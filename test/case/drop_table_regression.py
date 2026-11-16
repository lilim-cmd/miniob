#!/usr/bin/env python3
"""Run basic and DROP TABLE regressions against a built observer."""
import argparse
import logging
from pathlib import Path
import tempfile
import shutil
from contextlib import contextmanager

from update_regression import Server
from miniob_test import TestSuite, EvalResult


def run_basic(binary):
    project = binary.parent.parent.parent
    with tempfile.TemporaryDirectory(prefix='miniob-basic-') as directory:
        suite = TestSuite()
        suite.set_test_names(['basic'])
        suite.set_test_case_base_dir(str(project / 'test/case/test'))
        suite.set_test_result_base_dir(str(project / 'test/case/result'))
        suite.set_test_result_tmp_dir(str(Path(directory) / 'results'))
        suite.set_db_server_base_dir(str(binary.parent.parent))
        suite.set_db_data_dir(str(Path(directory) / 'data'))
        suite.set_db_config(str(project / 'etc/observer.ini'))
        suite.set_use_unix_socket(True)
        evaluation = EvalResult()
        suite.run(evaluation)
        assert 'basic is success' in evaluation.get_message(), evaluation.get_message()
        print('PASS: existing basic test', flush=True)


def table_dir(server, name):
    matches = list(server.directory.rglob(name + '.table'))
    assert len(matches) == 1, matches
    return matches[0].parent


def check_closed(server, files):
    descriptors = Path('/proc') / str(server.process.pid) / 'fd'
    if not descriptors.is_dir():
        return
    forbidden = {str(p.resolve()) for p in files}
    for descriptor in descriptors.iterdir():
        try:
            target = str(descriptor.readlink()).removesuffix(' (deleted)')
        except FileNotFoundError:
            continue
        assert target not in forbidden, ('dropped file descriptor still open', target)


def exercise(server):
    s = server
    s.fails('drop table does_not_exist;')
    s.ok('create table drop_me(id int, label char(8));')
    s.ok('create table drop_me_backup(id int);')
    s.ok('insert into drop_me_backup values(99);')
    s.ok('create index id_idx on drop_me(id);')
    s.ok('create index label_idx on drop_me(label);')
    for i in range(70):
        s.ok(f"insert into drop_me values({i}, 'item{i}');")
    s.rows('select id from drop_me where id=5;', [(5,)])
    s.ok('analyze table drop_me;')
    directory = table_dir(s, 'drop_me')
    files = [directory / name for name in (
        'drop_me.table', 'drop_me.data', 'drop_me-id_idx.index',
        'drop_me-label_idx.index', 'drop_me.lob', 'drop_me.table.tmp')]
    for file in files[:4]:
        assert file.is_file(), file
    # LOB storage is optional in this baseline. Its per-table file and a stale
    # metadata temporary file must still be removed if they are present.
    files[4].write_bytes(b'optional lob resource')
    files[5].write_bytes(b'stale table metadata')
    s.ok('drop table drop_me;')
    for file in files:
        assert not file.exists(), ('resource survived DROP TABLE', file)
    check_closed(s, files)
    assert 'drop_me' not in s.sql('show tables;').splitlines()[1:]
    for statement in (
        'drop table drop_me;', 'desc drop_me;', 'select * from drop_me;',
        "insert into drop_me values(1, 'x');", 'delete from drop_me;',
        'update drop_me set id=1;'):
        s.fails(statement)
    s.rows('select * from drop_me_backup;', [(99,)])

    # Same table name and index name can be reused with a different schema.
    s.ok('create table drop_me(id int);')
    s.ok('create index id_idx on drop_me(id);')
    s.ok('insert into drop_me values(123);')
    s.rows('select * from drop_me where id=123;', [(123,)])
    s.rows('select * from drop_me where id=5;', [])
    s.ok('drop table drop_me;')
    s.ok('create table empty_table(id int);')
    s.ok('drop table empty_table;')

    # An explicit transaction must not retain a freed Table pointer.
    s.ok('begin;')
    s.fails('drop table drop_me_backup;')
    s.ok('rollback;')
    s.rows('select * from drop_me_backup;', [(99,)])

    for i in range(10):
        s.ok('create table reuse(id int);')
        s.ok('create index reuse_idx on reuse(id);')
        s.ok(f'insert into reuse values({i});')
        s.rows(f'select id from reuse where id={i};', [(i,)])
        s.ok('drop table reuse;')
    assert not list(directory.glob('reuse.*'))
    assert not list(directory.glob('reuse-*.index'))
    assert not list(directory.glob('drop_me.*'))
    assert not list(directory.glob('drop_me-*.index'))


@contextmanager
def preserved_directory(trx):
    with tempfile.TemporaryDirectory(prefix=f'miniob-drop-{trx}-') as directory:
        try:
            yield directory
        except BaseException:
            destination = Path.cwd() / 'drop-table-failure' / trx
            shutil.copytree(directory, destination, dirs_exist_ok=True)
            for log in Path(directory).glob('observer.log*'):
                print(log.read_text(errors='replace')[-30000:], flush=True)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observer', type=Path)
    args = parser.parse_args()
    binary = args.observer.resolve()
    logging.basicConfig(level=logging.INFO)
    run_basic(binary)
    for trx in ('vacuous', 'mvcc'):
        with preserved_directory(trx) as directory:
            with Server(binary, directory, trx) as server:
                exercise(server)
            # Recovery must not resurrect deleted tables or require their files.
            with Server(binary, directory, trx) as server:
                server.fails('select * from drop_me;')
                server.fails('select * from reuse;')
                server.rows('select * from drop_me_backup;', [(99,)])
                server.ok('create table drop_me(id int);')
                server.ok('create index id_idx on drop_me(id);')
                server.ok('insert into drop_me values(456);')
                server.rows('select * from drop_me where id=456;', [(456,)])
                server.ok('drop table drop_me;')
                # Leave a committed read after the checkpoint to exercise
                # recovered-transaction cleanup on the next restart.
                server.rows('select * from drop_me_backup;', [(99,)])
            with Server(binary, directory, trx) as server:
                server.fails('desc drop_me;')
                server.rows('select * from drop_me_backup;', [(99,)])
                server.ok('drop table drop_me_backup;')
            with Server(binary, directory, trx) as server:
                server.rows('show tables;', [])
                server.ok('create table after_drop(id int);')
                server.ok('insert into after_drop values(7);')
                server.rows('select * from after_drop;', [(7,)])
                server.ok('drop table after_drop;')
            print(f'PASS: {trx}: DROP TABLE/resource cleanup/recreate/transactions/recovery', flush=True)


if __name__ == '__main__':
    main()

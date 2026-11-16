#!/usr/bin/env python3
"""Usage: python3 test/case/update_regression.py build/bin/observer"""
import argparse
from collections import Counter
from pathlib import Path
import socket
import subprocess
import tempfile
import time


class Server:
    def __init__(self, binary, directory, trx):
        self.binary = binary
        self.directory = Path(directory)
        self.trx = trx

    def __enter__(self):
        self.output = (self.directory / 'console.log').open('ab')
        config = self.binary.parent.parent.parent / 'etc' / 'observer.ini'
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        self.process = subprocess.Popen(
            [str(self.binary), '-f', str(config), '-p', str(port), '-t', self.trx, '-d'],
            cwd=self.directory, stdout=self.output, stderr=self.output)
        for _ in range(200):
            try:
                self.connection = socket.create_connection(('127.0.0.1', port), timeout=10)
                return self
            except (ConnectionRefusedError, ConnectionAbortedError):
                if self.process.poll() is not None:
                    raise RuntimeError((self.directory / 'console.log').read_text())
                time.sleep(0.05)
        self.process.terminate()
        self.process.wait(timeout=10)
        raise TimeoutError('observer did not become ready')

    def __exit__(self, *_):
        self.connection.close()
        self.process.terminate()
        self.process.wait(timeout=20)
        self.output.close()

    def sql(self, statement):
        self.connection.sendall(statement.encode() + b'\0')
        response = bytearray()
        while b'\0' not in response:
            part = self.connection.recv(65536)
            if not part:
                raise RuntimeError(f'observer closed connection: {statement}')
            response.extend(part)
        return response.split(b'\0', 1)[0].decode()

    def ok(self, statement):
        actual = self.sql(statement).strip()
        assert actual == 'SUCCESS', (statement, actual)

    def fails(self, statement):
        actual = self.sql(statement).strip()
        assert actual.startswith('FAILURE'), (statement, actual)

    def rows(self, statement, expected):
        actual = self.sql(statement).splitlines()
        assert actual and not actual[0].startswith('FAILURE'), (statement, actual)
        rows = Counter(tuple(cell.strip() for cell in line.split('|')) for line in actual[1:])
        expected = Counter(tuple(map(str, row)) for row in expected)
        assert rows == expected, (statement, rows, expected)


def exercise(s):
    s.ok('create table updates(id int, name char(8), age int, score float);')
    s.ok('create index updates_id on updates(id);')
    s.ok('create index updates_name on updates(name);')
    for i in range(1, 5):
        s.ok(f"insert into updates values({i}, 'Name{i}', {i}, {i}.5);")
    s.ok("update updates set name='X' where id=1;")
    s.rows("select * from updates where name='X';", [(1, 'X', 1, '1.5')])
    s.rows("select * from updates where name='Name1';", [])
    s.ok('update updates set age=10 where age>1 and age<4;')
    s.rows('select id from updates where age=10;', [(2,), (3,)])
    s.ok('update updates set id=20 where id=2;')
    s.rows('select id from updates where id=2;', [])
    s.rows('select name from updates where id=20;', [('Name2',)])
    s.ok('update updates set id=20 where id=3;')
    s.ok('update updates set id=20 where id=20;')
    s.rows('select age from updates where id=20;', [(10,), (10,)])
    s.ok('update updates set score=7;')
    s.rows('select score from updates;', [(7,)] * 4)
    s.ok("update updates set name='none' where id=999;")
    s.rows("select name from updates where name='none';", [])
    s.ok("update updates set name='';")
    s.rows("select name from updates where name='';", [('',)] * 4)
    for statement in (
        'update missing set age=1;', 'update updates set missing=1;',
        'update updates set age=1 where missing=1;',
        "update updates set age='invalid';", 'update updates set age=1 where another.id=1;'):
        s.fails(statement)
    s.rows('select id,age,score from updates;', [(1, 1, 7), (20, 10, 7), (20, 10, 7), (4, 4, 7)])
    s.ok('create table empty_table(id int);')
    s.ok('update empty_table set id=2;')
    s.rows('select * from empty_table;', [])
    s.ok("set execution_mode='chunk_iterator';")
    s.ok('update updates set age=9 where id=1;')
    s.ok("set execution_mode='tuple_iterator';")
    s.rows('select age from updates where id=1;', [(9,)])
    s.ok("set use_cascade='true';")
    s.ok('update updates set age=8 where id=4;')
    s.ok("set use_cascade='false';")
    s.rows('select age from updates where id=4;', [(8,)])
    s.ok('create table many(id int, name char(200));')
    s.ok('create index many_id on many(id);')
    for i in range(160):
        s.ok(f"insert into many values({i}, 'original');")
    s.ok('update many set id=42;')
    s.rows('select id from many where id=42;', [(42,)] * 160)
    s.ok("update many set name='short' where id=42;")
    s.rows('select name from many where id=42;', [('short',)] * 160)
    s.rows('select id from many where id=0;', [])
    s.ok('delete from updates where id=20;')
    s.ok("insert into updates values(5,'last',5,5.5);")
    s.rows('select id from updates;', [(1,), (4,), (5,)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observer', type=Path)
    args = parser.parse_args()
    binary = args.observer.resolve()
    for trx in ('vacuous', 'mvcc'):
        with tempfile.TemporaryDirectory(prefix=f'miniob-update-{trx}-') as directory:
            with Server(binary, directory, trx) as server:
                exercise(server)
                if trx == 'mvcc':
                    server.ok('begin;')
                    server.ok('update updates set id=99 where id=1;')
                    server.rows('select id from updates where id=99;', [(99,)])
                    server.ok('rollback;')
                    server.rows('select id from updates where id=1;', [(1,)])
                    server.rows('select id from updates where id=99;', [])
            with Server(binary, directory, trx) as server:
                server.rows('select id from updates;', [(1,), (4,), (5,)])
                server.rows('select id from many where id=42;', [(42,)] * 160)
            print(f'PASS: {trx}: conditional/all-row/index/error/chunk/cascade/multi-page/restart')


if __name__ == '__main__':
    main()

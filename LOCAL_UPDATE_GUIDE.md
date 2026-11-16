# MiniOB update 本地说明

项目目录：F:\oceanbase
当前分支：feat/update
基础版本：3259c37c8ddd8900ab045c8ce1fa1f5bf4d1e67d

## 推送到自己的仓库

在 PowerShell 中执行：

    cd F:\oceanbase
    git branch --show-current
    git push -u origin feat/update
    git rev-parse HEAD

origin 指向 https://github.com/lilim-cmd/miniob.git。
upstream 指向官方仓库。推送需要你自己的 GitHub 身份认证。

推送成功后，训练营 update 题填写自己的仓库地址、feat/update 分支和 git rev-parse HEAD 输出的完整编号。
basic 可以继续提交 main 分支原有提交。

## 分支不是另一个文件夹

    git branch
    git switch main
    git switch feat/update

切换分支会切换同一目录中的代码版本。

## 实现与验证记录

实现单字段 UPDATE：表/字段/类型及条件校验、逻辑计划、物理计划、索引维护、先快照后更新、MVCC 更新和索引回滚。
此目录根据本次会话中已验证的实现恢复；恢复时调整了注释和测试脚本排版。
此前 Linux 环境编译完成，并通过原有 basic 测试、新增 vacuous/MVCC 更新回归测试及部分解析/索引/记录单元测试。
这些历史运行记录不代表此 Windows 目录已经重新编译。当前 Windows 没有可用的 WSL Linux 发行版或 Docker，本次仅进行文件、Python 语法和 Git 差异检查。
训练营隐藏用例尚未验证，分数以平台结果为准。

Linux 构建完成后，可运行：

    python3 test/case/update_regression.py build/bin/observer

测试覆盖条件/全表/索引/重复键/空表/空字符串/错误输入/多页更新/执行模式/MVCC回滚/重启。

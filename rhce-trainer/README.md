# RHCE 9 逐题练习工具

程序在 Mac 本地运行，通过 f0 转入 KVM 虚拟机。核心程序不装在 workstation，重建虚拟机不会删除工具。题源为用户的《RHCE9.0模拟题新版(答案).pdf》，支持 19 道题。

## 安装与连接

需要 Python 3.9+、系统 OpenSSH。无需第三方 Python 库即可执行多数命令；16/17/18 的敏感题面值需 `pdfplumber`，会自动使用本机 Codex 附带的 Python（也可在自己的 Python 安装该库）。

```sh
cd /Users/wangrundong/work/红帽RHCE/rhce-trainer
./rhce list
./rhce connect
```

`connect` 通过终端输入 SSH 密码，不存储密码。默认连接 `root@rhce.lab0.cn:9007`，使用 OpenSSH 连接复用。新终端断线后重跑 connect。可用 `python3 -m pip install --user .` 安装为 `rhce`，或将本目录加入 PATH。

连接及 PDF 路径可保存到 `~/.local/state/rhce-trainer/connection.json`，只支持非秘密信息，例如：

```json
{"host":"rhce.lab0.cn","port":9007,"user":"root","pdf":"/Users/wangrundong/Downloads/RHCE9.0模拟题新版(答案).pdf"}
```

初次 SSH 主机密钥使用本机 OpenSSH 的 accept-new 信任策略；已有密钥变化会拒绝。内层实验 VM 会随重置变化，使用既有密钥登录且不向 f0 写 known_hosts。不要在配置加入密码。

## 日常使用

```sh
rhce list
rhce show 8
rhce plan 8
rhce reset 8 --dry-run
rhce reset 8
rhce grade 8
rhce grade 8 --verbose
rhce grade 8 --hint
rhce status
rhce doctor
```

`show` 只显示要求，不显示标准答案。答案在 workstation 的 `/home/devops/ansible` 中编写，所有 Ansible 命令由 devops 执行。可沿原路径登录 workstation，`su - devops` 后进入此目录。

`reset N` 会先备份答案、保存相关 VM 的整个现场，再恢复这些 VM 的已验证命名基线，准备依赖并移走本题产物。它会重置**相关 VM 的全部状态**，不只删除本题文件；不相关 VM 不动。旧答案还在本地备份和 workstation 的 `.rhce-trainer-retired` 中。不进行无备份的磁盘擦除。

第 10 题自动准备 research 卷组：a/b 可以容纳 600 MiB，c/d 只能完成 400 MiB，bastion 没有该卷组。第 11 题从空数据盘开始，与第 10 题隔离。第 9 题建立需要的网页及角色前提，第 17 题准备加密密码库。依赖图和题目产物在 `rhce_trainer/questions.json`。

## 首次初始化、恢复与中断

`rhce init` 是首次初始化操作：只处理五个受管节点，从官方原始 VM 镜像恢复，设置考试公共前提，并用官方 `rht-vmctl save` 保存命名基线。若发现已有保存点则停止，避免把用户最新保存点当成原始镜像。当前开发验证已建立基线时，不要再次 init。

```sh
rhce restore-lab --dry-run
rhce restore-lab
rhce recover <status 中的恢复点名称>
```

`restore-lab` 完全恢复五个受管练习节点至工具基线，控制节点答案保留。它不等同于 `fullreset all`：工具故意不提供会删除全部保存点、可能影响 utility 的宽泛命令。若真正需要重新下载损坏的 VM 主镜像，必须先导出保存点并在维护窗口单独处理，本工具不会自动这么做。

`recover` 恢复该操作保存的 VM 现场。控制节点答案归档在 `~/.local/state/rhce-trainer/backups`，不随 recover 自动覆盖，避免覆盖你后来继续写的答案。可先把 tar.gz 解压到本地临时目录查看，按需单文件还原。

## 评分原则

对于要求提交 playbook 的题目：

1. 检查产物、所有者和有效清单。
2. 保存当前 VM 现场，在命名基线上准备非考点前置条件。
3. 以 devops 从 `/home/devops/ansible` 运行你的 playbook。
4. 通过运行事件与系统实际状态判断各个 checkpoint。
5. 无论学生 playbook 成功或失败，都恢复评分前的 VM 现场。

因此手工 SSH 改对状态、空 playbook、只留下上次成功结果不能替代可重放的答案。角色和模板既检查产物也检查实际执行事件；不要求 YAML 与参考答案逐字相同。控制节点题直接验证有效配置、Galaxy 空目录安装、集合文件完整性、Vault 解密/内容保持。

每个检查点含 id、描述、权重、检查方式、PASS/FAIL 和证据。总分 100。基础设施无法恢复、依赖无法建立、无法采集时报告 ERROR，不冒充学生答案得分。退出码：0=满分/命令成功，1=未满分，2=环境/工具错误，130=中断。JSON 报告在 `~/.local/state/rhce-trainer/reports`。

## 题面冲突及覆盖边界

详见 `docs/analysis.md`，实际验收进度见 `docs/validation.md`。

- 第 12 题题面 IP 与环境冲突，默认按题面 172.25.254.10–13；`rhce grade 12 --profile live` 显式改按实际 172.25.250.10–13。报告记录模式。
- 第 13/14 题必须是 Development，不接受答案中的错拼 Devlopment。
- 第 5 题题面缺文件名，工具约定 selinux.yml。
- 第 11 题覆盖真实基线的 vdd 缺失、vdb=1 GiB 回退场景；不声称验证不存在的大盘分支。
- 这不是官方 RHCE 评分器，也不是恶意 Ansible 代码的安全沙箱。仅执行你信任的本次练习文件；清单地址、VM 名称及 UUID 有边界检查，但不允许把不可信脚本当作隔离任务交给它。

## 安全与维护

f0 仅执行只读探测及官方 VM 管理命令，不安装程序或修改物理网络、SSH、服务。utility/classroom 不在可重置白名单。保存点只使用显式名称，绝不使用可能恢复到“最新用户快照”的裸 reset 进行日常练习。VM 身份或官方脚本摘要发生变化时停止。

所有本地状态在仓库外的私有目录（700/600）；答案备份可能包含用户编写的秘密，不应提交仓库。题目密码从原 PDF 临时读取，通过 stdin 传输；不写入本地代码或配置。原始学生运行输出不自动落盘，防止意外日志泄密。

保存点会占用宿主机空间，低于 8 GiB 可用空间时拒绝新操作。本版本保留恢复点，不自动清理；维护时应确认不再需要后由环境管理员处理。中断后先看 status 并 recover，不要盲目重复初始化。

```sh
python3 -m unittest discover -s tests -v
```

扩展题目：在 questions.json 定义要求、依赖、产物、影响节点，在 engine.py 加准备步骤，在 graders.py 注册独立评分函数；权重必须合计 100，并增加正反例验证。

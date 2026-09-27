# RHCE 9 逐题练习工具

程序在 Mac 本地运行，通过 f0 转入 KVM 虚拟机。核心程序不装在 workstation，重建虚拟机不会删除工具。题源为用户的《RHCE9.0模拟题新版(答案).pdf》，v0.1.0 已接入全部 19 道题的题面、依赖准备、reset 和评分函数。11 道题已有实机满分记录，其余验收范围和限制见 [验收记录](docs/validation.md)。

## 安装与连接

需要 Python 3.9+、系统 OpenSSH。无需第三方 Python 库即可执行多数命令；16/17/18 的敏感题面值需 `pdfplumber`，会自动使用本机 Codex 附带的 Python（也可在自己的 Python 安装该库）。

```sh
cd /你的项目目录/rhce-trainer
./rhce list
./rhce connect
```

`connect` 通过终端输入 SSH 密码，不存储密码。默认连接 `root@rhce.lab0.cn:9007`，使用 OpenSSH 连接复用。新终端断线后重跑 connect。可用 `python3 -m pip install --user .` 安装为 `rhce`，或将本目录加入 PATH。

普通电脑推荐在虚拟环境安装完整版本（包含密码题所需 PDF 读取库）：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[pdf]'
rhce list
rhce connect
rhce doctor
```

连接及 PDF 路径可保存到 `~/.local/state/rhce-trainer/connection.json`，只支持非秘密信息，例如：

```json
{"host":"rhce.lab0.cn","port":9007,"user":"root","pdf":"/你的资料目录/RHCE9.0模拟题新版(答案).pdf"}
```

直接从源码运行时会自动寻找项目旁的 RHCE9.0 PDF；安装为独立包后，应在 connection.json 指定 PDF 路径。

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

`plan N` 和 `reset N --dry-run` 可离线查看完整依赖顺序、重置 VM 范围和评分 VM 范围。第 12 题仅重置 servera，但为收集全部主机事实，评分会临时保存、恢复五台受管节点。

`reset N` 会先备份答案、保存相关 VM 的整个现场，再恢复这些 VM 的已验证命名基线，准备依赖并移走本题产物。它会重置**相关 VM 的全部状态**，不只删除本题文件；不相关 VM 不动。旧答案还在本地备份和 workstation 的 `.rhce-trainer-retired` 中。不进行无备份的磁盘擦除。

重置和评分都可能耗时数分钟：官方 VM 启动流程结束后才开始操作，评分还需要恢复原现场。请等命令退出后再编辑答案或运行下一条操作。

第 10 题自动准备 research 卷组：a/b 可以容纳 600 MiB，c/d 只能完成 400 MiB，bastion 没有该卷组。第 11 题从空数据盘开始，与第 10 题隔离。第 9 题建立需要的网页及角色前提，第 17 题准备加密密码库。依赖图和题目产物在 `rhce_trainer/questions.json`。

## 首次初始化、恢复与中断

`rhce init` 是首次初始化操作：只处理五个受管节点，从官方原始 VM 镜像恢复，设置考试公共前提，并用官方 `rht-vmctl save` 保存命名基线。若发现已有保存点则停止，避免把用户最新保存点当成原始镜像。已有基线时，普通 init 拒绝运行；需要补齐公共准备可显式使用 `rhce init --prepare`，详见下文。

```sh
rhce restore-lab --dry-run
rhce restore-lab
rhce recover <status 中的恢复点名称>
rhce recover <status 中的恢复点名称> --with-answers
```

`restore-lab` 完全恢复五个受管练习节点至工具基线，控制节点答案保留。它不等同于 `fullreset all`：工具故意不提供会删除全部保存点、可能影响 utility 的宽泛命令。若真正需要重新下载损坏的 VM 主镜像，必须先导出保存点并在维护窗口单独处理，本工具不会自动这么做。

如果迁移了电脑或丢失本地状态，但原有基线仍在 f0，可使用明确的名称接管：

```sh
rhce adopt-baseline rhce-baseline-20260926225159-5dbbe3
rhce doctor
```

上面的名称是本次环境实际发现的保存点，不能照搬到其他环境。接管只读取身份和每台 VM 的全部磁盘保存点，再写本地绑定；不会重置 VM，也不等于重新验证保存点内容。已有本地基线时默认拒绝覆盖。若环境已经重建，先核对新保存点和 VM 身份，再显式执行 `rhce adopt-baseline <新保存点名称> --replace`。只有全部磁盘检查成功后才会切换绑定；旧身份、基线和练习状态保留在本地 `previous-binding-*.json`。

`recover` 恢复该操作保存的 VM 现场。控制节点答案归档在 `~/.local/state/rhce-trainer/backups`，默认不随 recover 覆盖；显式加入 `--with-answers` 可一并恢复答案，当前文件会移到 retired 目录保留。reset 自身失败时自动回滚本次答案修改。可先把 tar.gz 解压到本地临时目录查看，按需单文件还原。

## 评分原则

对于要求提交 playbook 的题目：

1. 检查产物、所有者和有效清单。
2. 保存当前 VM 现场，在命名基线上准备非考点前置条件。
3. 以 devops 从 `/home/devops/ansible` 运行你的 playbook。
4. 通过运行事件与系统实际状态判断各个 checkpoint。
5. 无论学生 playbook 成功或失败，都恢复评分前的 VM 现场。

因此手工 SSH 改对状态、空 playbook、只留下上次成功结果不能替代可重放的答案。角色和模板既检查产物也检查实际执行事件；不要求 YAML 与参考答案逐字相同。控制节点题直接验证有效配置、Galaxy 空目录安装、集合文件完整性、Vault 解密/内容保持。

每个检查点含 id、描述、权重、检查方式、PASS/FAIL 和证据。已完成可靠基线重放后，即使某台主机执行失败，其他已满足要求的分项仍可得分；运行失败独立扣除执行分。总分 100。基础设施无法恢复、依赖无法建立、无法采集时报告 ERROR，不冒充学生答案得分。退出码：0=满分/命令成功，1=未满分，2=环境/工具错误，130=中断。JSON 报告在 `~/.local/state/rhce-trainer/reports`。

## 题面冲突及覆盖边界

详见 `docs/analysis.md`，实际验收进度见 `docs/validation.md`。

- 第 12 题题面 IP 与环境冲突，默认按题面 172.25.254.10–13；`rhce grade 12 --profile live` 显式改按实际 172.25.250.10–13。报告记录模式。
- 第 13/14 题必须是 Development，不接受答案中的错拼 Devlopment。
- 第 5 题题面缺文件名，工具约定 selinux.yml。
- 第 11 题覆盖真实基线的 vdd 缺失、vdb=1 GiB 回退场景；不声称验证不存在的大盘分支。
- 这不是官方 RHCE 评分器，也不是恶意 Ansible 代码的安全沙箱。仅执行你信任的本次练习文件；清单地址、VM 名称及 UUID 有边界检查，但不允许把不可信脚本当作隔离任务交给它。

## 安全与维护

f0 仅执行只读探测及官方 VM 管理命令，不安装程序或修改物理网络、SSH、服务。utility/classroom 不在可重置白名单。保存点只使用显式名称，绝不使用可能恢复到“最新用户快照”的裸 reset 进行日常练习。VM 身份或官方脚本摘要发生变化时停止。保存和恢复时会在 VM 停止状态下逐磁盘比较保存点与当前镜像，防止官方脚本未传播复制错误而误报成功。

reset 在修改前检查下载资源及密码题所需的 PDF；资源不可达时停止，不先清除答案。重置完成后独立检查本题文件缺失、SSH 提权可用和关键磁盘前置条件。

本地操作锁与 workstation 上的跨电脑操作锁共同防止新版工具并发重置。该锁不会阻止旧版工具或手工操作，因此现场验收仍需确认没有其他使用者。锁断开会停止后续远程操作；重置或全环境恢复失败会尝试恢复已保存的 VM 现场。控制节点文件仍通过备份单独恢复。若无法确认学生运行进程已停止，则保留 recovery_required，避免活跃进程继续污染恢复后的 VM。

所有本地状态在仓库外的私有目录（700/600）；答案备份可能包含用户编写的秘密，不应提交仓库。题目密码从原 PDF 临时读取，通过 stdin 传输；不写入本地代码或配置。原始学生运行输出不自动落盘，防止意外日志泄密。

保存点会占用宿主机空间，低于 8 GiB 可用空间时拒绝新操作。本版本保留恢复点，不自动清理；维护时应确认不再需要后由环境管理员处理。中断后先看 status 并 recover，不要盲目重复初始化。

```sh
python3 -m unittest discover -s tests -v
```

开发者现场验收（需独占环境）：

```sh
python3 tests/live_cases.py --apply 13 8 10
```

验收脚本会保存所选题实际涉及的受管 VM 和控制节点答案，逐题 reset、写入测试提交、grade，最后恢复原 VM 及答案；测试提交留在 `.rhce-trainer-retired` 供排查。未传 `--apply` 会拒绝运行。追加 `--negative` 会先建立正确系统状态，再换成空 playbook，验证旧状态不会被误判为满分。基础设施或恢复错误必须先处理，不能当作学生未得分。

扩展题目：在 questions.json 定义要求、依赖、产物、影响节点，在 engine.py 加准备步骤，在 graders.py 注册独立评分函数；权重必须合计 100，并增加正反例验证。

## 快速检查与公共准备（新增）

已经手动运行 YAML 后，可以直接检查当前状态：

```sh
rhce grade 8 --fast
rhce grade 8 --fast --verbose
rhce grade 12 --fast --profile live --json
```

| 行为 | `rhce grade N` | `rhce grade N --fast` |
|---|---|---|
| 受管节点 | 保存现场、恢复基线、准备依赖、执行提交，最后恢复现场 | 只读取当前状态和提交文件 |
| 执行证据 | 检查本次角色、模板、下载、错误分支等事件 | 标记为 `UNVERIFIED`（未验证） |
| 控制节点特殊检查 | 包含 Galaxy 空目录安装验证 | 不安装角色，不加载提交的清单插件 |
| 分数 | 完整评分，满分 100 | 得分 / 可验证项权重；不能与完整评分直接比较 |

快速报告明确显示“快速检查”，逐项列出通过、失败和未验证；JSON 的 `passed` 分别为 `true`、`false`、`null`。`maximum` 是可验证项目的权重合计，`percentage` 是这些项目的通过比例；没有可验证项目时为 `null`。例如第 13 题正确现状可得 **75/75**，另有执行成功 20 分和清单主机执行范围 5 分未验证；这不等于完整评分 100 分。

快速模式保留文件存在性及 devops 所有者检查，复用软件包、服务、配置文件、磁盘、用户、定时任务及 HTTP 等适用检查。混合状态与事件的检查点整体保守标为未验证：例如第 10 题 c/d 的容量回退和 bastion 缺卷组提示。第 3 题的 DNF 组/最新版本检查可能更新缓存或日志，快速模式不运行；第 6 题的安装可用性与完整性需要临时安装参考角色，也不运行。第 1 题仅检查提交文件和软件包，不加载可能执行代码的清单/配置插件。第 16–18 题仍需题面密码/资源，缺少必要资料会报环境错误。

快速检查不获取会创建远程锁文件的跨电脑锁，不运行 playbook，不准备依赖，不备份、保存、恢复、重启 VM。只在本地保存评分报告；SSH/HTTP 访问可能产生服务端正常访问日志。检查期间请勿同时修改实验环境或执行 reset，以免观察结果跨越不同状态。退出码 0 表示可验证项没有失败，**不表示未验证项通过**；1 表示存在失败，2 表示环境/工具错误。

已有基线时，使用显式补齐命令：

```sh
rhce init --prepare
```

该命令核对当前身份和已有基线全部磁盘，再逐项完成以下公共准备：

- workstation 将 `/root/.ssh/lab_rsa` 复制为 devops 的 `/home/devops/.ssh/id_rsa`，权限 600；公钥由该私钥导出。
- 五台受管节点确保 devops、公钥及免密 sudo 就绪；bastion 的 devops 密码设为 `redhat`。保留 authorized_keys 内已有其他公钥。
- 从 workstation 以 devops、SSH BatchMode 验证 servera–serverd、bastion 的免密登录与 `sudo -n`。
- 备份后清理五台节点 `/etc/yum.repos.d/*.repo`；重复清理不覆盖以前的同名备份。
- 写入 devops 的 `~/.ansible-navigator.yml`，使用 `utility.lab.example.com/ee-supported-rhel8:latest` 和 `execution-environment.pull.policy: missing`，再检查有效设置。格式依据 [Navigator 配置文档](https://docs.ansible.com/projects/navigator/settings/)。
- 写入 devops 的 `~/.config/containers/registries.conf`，把 `utility.lab.example.com` 设为搜索仓库和不安全仓库。用当前 Podman 先探测 v2 格式，必要时尝试旧格式，最后读取默认配置的有效结果验证；不拉取镜像。验证方式参见 [Podman info 文档](https://docs.podman.io/en/latest/markdown/podman-info.1.html)。

原有私钥、配置和 repo 文件在对应 VM 的 `/root/.rhce-common-backups/<唯一编号>/` 下按原绝对路径保存；重复执行时相同配置不重复备份。不会修改 `/home/devops/ansible` 中的答案。注意 repo 清理会影响当前第 2 题等练习状态，因此只在需要重新准备公共环境时显式执行。

`init --prepare` **不重置、停止或保存 VM，也不创建或更新基线**。旧基线仍保持原样，日后恢复旧基线可能撤销受管节点上的此次补齐；必要时再次显式补齐，或由管理员另建并核对新保存点后 `adopt-baseline`。没有基线时该命令也只准备，不建立基线。

首次 `rhce init` 保留原有原始镜像重置流程和已有保存点保护，只有公共准备全部通过、空数据盘检查通过之后才保存新基线。任何公共步骤失败或跳过，整体退出为错误，不输出初始化完成。逐项结果存入本地 `reports/*-init.json`，其中 `complete: false` 表示公共准备不完整；`complete: true` 仅表示公共准备成功，基线是否保存成功以最终命令结果和 `baseline.json` 为准。准备失败时已完成的公共修改及其备份保留，可修复问题后重试；不会把部分成功当成基线建立完成。若保存基线中断，保留已创建保存点，不会通过重复 init 自动覆盖。

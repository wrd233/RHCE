# 认识 Ansible

先不要急着背 YAML。第一章最重要的是建立一个画面：Ansible 到底在谁身上运行、它怎么找到机器、怎么把“我要这个状态”变成远端动作。

我们先把 Ansible 放回你刚学完 RHCSA 的世界里看。RHCSA 里你做事情的方式通常是：SSH 到机器上，执行 `useradd`、`dnf install`、`systemctl`、改配置文件。Ansible 并没有创造一套新的 Linux，它只是把这些“对系统对象的操作”抽象成了可以批量、重复、声明式执行的任务。所以你一开始不要把它想成编程语言，先把它想成一个**远程批量执行 + 状态管理的工具箱**。

我们先抓住五个特点：能管理云、网络设备、Linux/Windows、存储；通常借助设备已有的连接方式接管，不要求每台 Linux 节点常驻一个 Ansible Agent；没有必须长期运行的中心服务；Ansible 本身是工具而不是常驻 daemon；功能通过大量模块扩展。这里有一个特别值得形成的心智模型：**“控制节点”是一次执行中的角色，不是一个必须永远存在的中心服务器。**哪台机器装了 Ansible、拿着 inventory 和 playbook 发起任务，哪台机器就可以扮演控制端。

先记住这一条执行链：Playbook / Ad-hoc → Inventory 选主机 → Module 描述动作 → Connection Plugin 连接 → 远端执行 → 返回 ok / changed / failed

我把执行过程拆成 **ansible、inventory、modules、plugins**。这个拆法非常适合考试。你以后看到任何题都可以问四句：我要从哪个项目目录发起？目标主机在哪个组？我应该调用哪个模块？这个模块需要怎样连接、提权、读取变量？你会发现，绝大多数 RHCE 题只是把这四个东西重新组合。

### Inventory：Ansible 的“通讯录”

它不是单纯列 IP。它还表达主机组、组嵌套以及与主机有关的变量。Ansible 默认只会对 inventory 中能选中的目标执行任务。因此考试里第一题为什么重要？因为后面几十个 task 都建立在“目标集合选对了”这个前提上。

### Module：真正完成动作的“动词”

`user` 管用户，`yum/dnf` 管包，`file` 管文件对象，`firewalld` 管防火墙。你不需要背完整 YAML，只需要先会把题目里的名词翻译成模块，然后用 `ansible-doc -s 模块名` 查参数。

### Ansible 2.9 之后为什么总在讲 ansible-core 和 collection？

版本变化可以这样理解：以前大家口中的 “Ansible” 更像一大包东西；后来核心执行引擎和大量可扩展内容逐渐拆开。你在 RHEL 9 / RHCE 9 环境里更应该形成的理解是：**ansible-core 提供执行框架与核心内容，Collection 是可独立发布的一组 modules、plugins、roles。**这也是为什么某些模块明明你在网上见过，考试环境里却可能暂时“没有”——不是 Ansible 不会，而是对应集合还没装。

Collection 之后又引出了 FQCN（完全限定集合名），比如 `ansible.builtin.yum`。考试里短模块名经常也能用，但你要看得懂完整名字，因为帮助文档、官方示例和 collection 内容经常按 FQCN 写。

### Navigator：把“执行 Ansible 的环境”也固定下来

我们先把 `ansible-navigator` 理解为“在受控执行环境里运行 Ansible”。传统 `ansible-playbook` 直接使用宿主机上的 Python、Ansible、Collection；Navigator 则借助 Execution Environment 镜像，把执行工具链放到容器里。这样同一份 playbook 可以在更稳定、更可控的依赖环境中运行。你到后面会单独学它，现在先记住：**Playbook 没变，换的是执行它的环境。**

### 安装方式：RPM、pip、源码，考试里要分清“知识”和“动作”

Ansible 可以通过 RPM 仓库、pip 或源码安装；在离线环境，也可能通过本地 ISO 提供软件仓库。它们很适合帮助你理解 Ansible 本质上就是 Python 世界里的一个工具，但备考时没必要平均用力。RHCE 环境更重要的是确认现有的 `ansible-core`、`ansible-navigator`、system roles、collections 到底在哪里，以及配置文件实际从哪里读。

```
ansible --version
ansible-config dump --only-changed
ansible-config view
ansible-doc -l | head
```

其中 `ansible --version` 很有价值，因为它会告诉你当前生效的配置文件、模块路径、collection 路径、Python 版本。出现“我明明写了配置为什么没生效”时，这个命令比盯着文件猜要高效得多。

**精确一点：**我们可以先把普通 Linux 主机上的模块执行理解为“封装 Python 脚本发送过去再执行”。这个模型对入门足够好，但别把它当成所有目标都完全一样：网络设备、`raw`、某些 action/connection plugin 的执行路径会不同。考试里不需要钻这个实现细节，你只要知道为什么大多数 Linux 管理模块依赖远端 Python，而 `raw` 可以绕过模块子系统做最底层的命令执行。

### ansible.cfg 为什么有那么多选项？

不是让你背。真正想让你看到的是：Ansible 的行为几乎都可以配置，例如 inventory、roles 路径、是否检查 host key、远程用户、Vault 密码文件、fact 收集、SSH 连接、回调插件、颜色、diff 等。考试策略是**只写题目要求的最小配置**，剩下使用默认值。完整模板适合作为“字典”，不适合作为背诵材料。

### 从一条命令看清整条链

我们拿模拟练习里的 `servera` 做例子。假设当前目录有 `inventory`，其中 `[dev]` 下面写了 `servera`，那么 `ansible dev -m ansible.builtin.ping` 的意思是：从清单选出 dev 组的主机，通过连接插件登录，把 ping 模块送到受管节点执行，再把结果带回来。这里的 `ping` 不是 ICMP 网络探测，它主要检查 Ansible 能否通过既定连接方式在远端运行模块。接着用 `ansible dev --list-hosts` 检查目标集合，用 `ansible dev -m ansible.builtin.setup -a 'filter=ansible_distribution*'` 看远端系统信息，整条链就有了实物。

```text
项目目录里的 ansible.cfg → 找到 inventory → 选中 dev/servera
                       → 以 remote_user 登录 → become 提权
                       → 运行模块 → 收到 ok、changed、failed 或 unreachable
```

如果返回 `unreachable`，我先查主机名、SSH、密钥和远程用户；如果登录成功却报 `permission denied`，我查提权；如果提示找不到模块，我查 collection 与执行环境。**同一条任务链，故障点不同，排查入口也不同。**

### 安装知识该学到哪里

RPM 安装让软件包与系统仓库集成；pip 更适合隔离的 Python 环境；源码安装适合开发或特定版本实验。知道这些路径，我们就能理解 Ansible 的运行依赖来自哪里。回到这套模拟题，第 1 题真正要交付的是可运行的项目配置、清单和后续 Playbook；如果环境已有 `ansible-core` 与 `ansible-navigator`，先检查版本和配置文件即可，不必为了重做安装破坏现成环境。

### 自动化为什么值得做，以及比较工具时看什么

重复巡检、配置发放和故障处理如果每次都靠人登录几十台机器，速度、统一性和事后追溯都会受到影响。把预期状态写成可复跑的任务以后，我们能减少重复劳动、保留配置变更的来龙去脉，也更容易把同一套做法推广到更多节点。这里的关键并不是“机器能替人敲命令”，而是**结果可描述、执行可重复、变化可检查**。

课程也拿 Puppet、SaltStack 等工具做过比较。对我们此时的学习最有用的差异，是 Ansible 常见的 SSH 连接方式、控制端发起任务和无需给每台 Linux 主机常驻安装独立 Agent；其他工具的支持系统、难度或生态会随版本变化，不能把旧表格里的绝对判断当成今天的事实。你只需要记住 Ansible 的“清单—连接—模块—结果”模型，后面所有章节都在扩展它。

### 一点历史，帮助我们理解生态为何拆分

回看发展脉络，Ansible 在 2012 年面世，2015 年进入红帽生态，之后从一个容易上手的自动化工具逐渐扩展出更多模块、角色和集合。时间线本身不是这套模拟题的得分点；我们提它，是为了理解为什么今天会同时遇到 `ansible-core`、Collection、Galaxy 和 Execution Environment 这些名字。它们不是四套互不相干的工具，而是在“执行引擎、可复用内容、内容分发、执行环境”四个位置分工。

### 模块与插件在架构里各做什么

我们前面用 `user`、`dnf`、`file` 这些模块描述受管节点要达到的状态。连接插件负责怎样到达节点，其他插件还可能处理回调输出、日志或额外的数据读取；所以看到“插件”时，不要只想到模块名。把整张架构图放进脑海里：清单和 Playbook 进入 Ansible 执行器，执行器选模块并借助连接插件到达多台目标，结果再交给输出/日志等插件呈现。考试最常写的是清单、任务与模块，但执行故障往往发生在连接或内容加载环节。

<!-- EXAM -->

**考试连接：**这一章最直接对应模拟题第 1 题（安装与配置 Ansible），同时给第 6/7 题 Galaxy/Collection、第 13 章 Navigator 打底。考场上你真正要熟的是 `ansible --version`、项目目录、inventory、`ansible.cfg` 和连通性验证，而不是三种安装方法全部手敲一遍。

<!-- EXERCISE -->

**随堂想一想：**如果你在 A 目录里运行 `ansible all -m ping` 正常，切到 B 目录后突然发现主机组不存在，你第一反应应该查什么？

<details markdown="1"><summary>看答案</summary>

先运行 `ansible --version` 看当前加载了哪个配置文件，再看 inventory 配置。这个问题本质上不是“网络断了”，而是“执行上下文变了”。

</details>

# Ansible Navigator

最后把执行方式收回来：你前面学的 Inventory、Playbook、Role、Collection 都没变；Navigator 只是把“执行器”放进一个可控的容器环境。

传统方式是 `ansible-playbook xxx.yml`；Navigator 常见考试写法是：

```
ansible-navigator run xxx.yml -m stdout
```

`-m stdout` 让输出更接近普通 ansible-playbook，备考时最直观。交互模式也能看结果，但考试做题强调速度和可预期输出，stdout 通常更顺手。

### Execution Environment：为什么要用容器镜像

它把 Ansible 版本、Python 依赖、部分 collections/plugins 固定在镜像中，避免“我机器上的环境和你机器不一样”。因此选择不同 EE 就可以切换 Ansible 的执行依赖。这个思想和容器化应用是一样的：不是把受管节点装进容器，而是把**自动化执行工具链**装进容器。

### 镜像拉取策略：missing 是备考里最容易理解的设置

如果 pull policy 过于积极，Navigator 可能尝试联网拉 registry.redhat.io 的镜像并遇到认证/网络问题。本地镜像已就绪时可以设为 `missing`：本地已有镜像就直接用，没有才拉。这也是你模拟题准备环境里 `.ansible-navigator.yml` 的重要配置。

```
ansible-navigator:
  execution-environment:
    enabled: true
    image: utility.lab.example.com/ee-supported-rhel8:latest
    pull:
      policy: missing
  mode: stdout
```

### 为什么当前工作目录如此重要

按这套 RHCE 训练材料，最安全的工作流就是始终在题目指定项目目录（例如 `/home/devops/ansible`）运行 Navigator，并把 `ansible.cfg`、inventory、roles、collections 都按项目相对关系组织好。容器化执行会让“宿主机随便哪个目录里的东西都天然可见”这种直觉失效，所以**不要随意 cd 到别处再跑**。

### Artifact 与 replay

Navigator 可以保存 playbook artifact JSON，里面记录执行结果。需要回看时可以 replay。备考不一定要求你深入 artifact schema，但要知道看到项目目录里多出来 JSON 并不是“垃圾文件”，而是一次运行的结构化记录。

### Galaxy 仍然是 Galaxy

我们也要记住：Role/Collection 的安装管理仍使用 `ansible-galaxy`；Navigator 主要负责运行/探索自动化内容。考试里别看到 Navigator 就把所有命令都改写成 `ansible-navigator galaxy ...`。

**考试边界：**这套训练材料把重点放在“通过 Navigator 运行 Playbook”上；至于正式考试的具体要求，应以参加考试时的官方说明为准。就本套模拟练习而言，会确认镜像、会在正确目录运行、会 `-m stdout`，就已经覆盖最重要的考试动作。

### 用同一题检验执行上下文

把第 2 题的 `yum_repo.yml` 放在项目目录，先看 `ansible-navigator --version` 和 `ansible-navigator images`，确认可用镜像，再在该目录运行 `ansible-navigator run yum_repo.yml -m stdout`。当它和 `ansible-playbook yum_repo.yml` 表现不同时，优先比较两次使用的 Ansible/Collection 版本、镜像、项目挂载路径和配置文件。Navigator 的 stdout 模式只是输出方式，**真正影响执行的是 EE 与项目可见性**。

```yaml
# ~/.ansible-navigator.yml 示例；镜像地址属于这套练习环境
ansible-navigator:
  execution-environment:
    image: utility.lab.example.com/ee-supported-rhel8:latest
    pull:
      policy: missing
```

`missing` 只控制“本地没有镜像时才拉取”，并不保证离线环境一定能运行：本地镜像仍需存在，容器运行时也得可用。模拟题准备步骤中的 SSH 密钥复制、私有仓库登录和节点仓库清理属于练习场景准备；答题时先看给定环境，避免把这些操作误当成每一题都要执行的固定开场。交付的 Playbook 和配置文件要能在题目规定的控制节点目录中重新运行，这一点比终端里一时显示 `changed=0` 更重要。

<!-- EXAM -->

**考试连接：**这套模拟练习最终是在“项目目录 + ansible.cfg + inventory + playbook/roles/collections + navigator”这套工程里工作。最稳的习惯是每完成一题都在同一项目根目录运行，并用系统命令做最终状态验证。

<!-- EXERCISE -->

**最后一个随堂问题：**`ansible-playbook users.yml` 能跑，但 `ansible-navigator run users.yml -m stdout` 找不到你刚安装的 collection。你应该从什么角度排查？

<details markdown="1"><summary>答案</summary>

先意识到两次执行环境不同。检查 Navigator 使用的 EE、项目目录、ansible.cfg 的 collection 搜索路径，以及 collection 是否在 EE/项目挂载可见的路径中。不要先怀疑 YAML。

</details>

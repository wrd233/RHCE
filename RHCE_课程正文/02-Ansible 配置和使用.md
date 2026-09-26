# Ansible 配置和使用

这一章要把“我是谁、我要连谁、连上去以后以谁的身份做事”彻底分开。很多初学者所有配置混在一起，错就错在这里。

`ansible.cfg` 其实是在给执行器一个默认工作环境。我们先抓最常见的几项：inventory 在哪、是否询问 SSH 密码、默认远程用户是谁、是否做 host key 检查、roles/collections 去哪里找，以及 privilege escalation（提权）怎么做。

远程执行的两个身份不要混：控制端当前用户 → remote\_user / ansible\_user 登录远端 → become → become\_user（常见 root）执行任务

例如这里的配置写了 `remote_user = devops`，又在 `[privilege_escalation]` 中写 `become=True`、`become_user=root`。它表达的是：SSH 先以 devops 登录，再通过 sudo 变成 root 做管理任务。这个区分非常重要，因为考试中“SSH 连不上”和“sudo 提权失败”是两类完全不同的问题。

```
[defaults]
inventory = /etc/ansible/hosts
ask_pass = False
remote_user = devops

[privilege_escalation]
become = True
become_method = sudo
become_user = root
become_ask_pass = False
```

如果是在自己搭建的练习环境，可以先用 root 建立 devops、配置 SSH 密钥和 sudo 权限，再用 devops 执行自动化。这一步让我们看到**Ansible 自己也需要“可连接、可提权”的先决条件**。如果题目环境已经准备好了这些条件，先验证即可，不要把搭环境的动作混进答题文件。

### 配置文件优先级：这是非常容易被忽略的排错知识

配置文件的查找顺序是：`ANSIBLE_CONFIG` 环境变量 → 当前目录 `ansible.cfg` → 用户家目录 `~/.ansible.cfg` → `/etc/ansible/ansible.cfg`。你不用每天背，但一定要知道“当前目录配置的优先级很高”。所以项目化做题时把 `ansible.cfg` 放在题目规定的项目目录里，是最稳妥的。

当你怀疑配置读错，别凭感觉：`ansible --version` 会显示 config file；`ansible-config dump --only-changed` 可以看非默认配置。

### Inventory：先学表达集合，再学写 YAML

我们先写单台主机，再把主机放进组，最后用 children 把组嵌套起来。你可以把 inventory 理解成一张“集合关系图”。例如 `[webservers]` 是一个集合；`[servers:children]` 表示 servers 这个大集合由其他组组成。

```
[webservers]
web1
web2

[mysqlservers]
db1

[servers:children]
webservers
mysqlservers
```

考试里的 `prod` 作为 `webservers` 的 child 就是这个模型。你不需要把一台机器在多个地方复制来复制去，组嵌套能让“角色集合”更清楚。

### 主机选择模式：把它当成集合运算

`all` 是全集；一个组名是子集；逗号可以选择多个模式；通配符和正则可以匹配名称。实际备考中我建议你在执行修改性任务前养成一个动作：先 `--list-hosts`。尤其是组嵌套题，先确认你选中的到底是谁，再执行。

```
ansible all --list-hosts
ansible webservers --list-hosts
ansible 'web*' --list-hosts
ansible '~^m|^w' --list-hosts
```

**精确一点：**如果你把未分组主机写在某个 `[group]` 标题后，它会被归进这个组。真正重要的是 inventory 的 INI 语法边界：在一个 `[group]` 标题之后的主机都属于该组，直到下一个 section。所谓“写在上面”是在提醒你别无意中把裸主机放进前一个组里。

### 把第 1 题完整写成一个项目

我们现在照模拟题的主机关系写一遍。`servera` 在 dev，`serverb` 在 test，`serverc/serverd` 在 prod，`bastion` 在 balancers；`webservers` 是 prod 的父组。请留意最后两行：它们在表达组与组的关系，不是再列一次主机。

```ini
[dev]
servera
[test]
serverb
[prod]
serverc
serverd
[balancers]
bastion
[webservers:children]
prod
```

项目的 `ansible.cfg` 可以先写最少的必要项。下面的地址、用户与路径来自这套模拟练习；换环境时按题面调整。`/etc/ansible/hosts` 是一个常见默认位置，但这里必须用题目要求的项目清单，不能照搬。

```ini
[defaults]
inventory = /home/devops/ansible/inventory
remote_user = devops
roles_path = /home/devops/ansible/roles
collections_path = /home/devops/ansible/mycollections

[privilege_escalation]
become = True
become_method = sudo
become_user = root
```

这时我会按顺序验证：`ansible --version` 确认配置文件，`ansible-inventory --graph` 看组关系，`ansible webservers --list-hosts` 确认恰好是 serverc/serverd，再用 `ansible all -m ansible.builtin.ping` 验证连接。若配置项名称因现场版本有差别，用 `ansible-config list` 查当时版本认可的键；不要把模拟题答案里排版断开的 `host_key_checkin g` 当成可用配置。

另外，`ANSIBLE_CONFIG` 可以显式指定配置文件，但 Ansible 对不安全目录中的本地配置有额外保护。遇到“明明在当前目录却没读到”时，以 `ansible --version` 显示的实际路径为准，再核对目录权限，而不是只靠优先级表猜。

### 范围、并集与连接方式

清单可以用范围压缩重复主机名，例如 `web[01:50].example.com` 表示连续的 web01 到 web50，`db-[a:f].example.com` 表示六台 db 主机。主机匹配也可以用组名、通配符和正则；多个组取并集时，`dev:test:prod` 的语义更清楚。任何可能修改远端系统的命令，我都会先用 `--list-hosts` 看实际命中的主机。

连接身份还可以写成清单变量：`ansible_host` 指真实地址，`ansible_user` 指登录用户，`ansible_port` 指端口，`ansible_ssh_private_key_file` 指私钥，`ansible_become` 等变量控制提权。比如主机别名是 `web1`，真实地址是 `172.25.250.10`，那么 `inventory_hostname` 仍是 `web1`。这能解释为什么“能 SSH 到 IP”却“Ansible 找不到 web1”或最终输出的主机名与地址不同。

在自己的实验环境里，如果 devops 尚不能免密登录，可先准备用户、授权 sudo 并分发 SSH 公钥，然后从控制端测试 `ssh devops@servera`。这属于连接前置条件；模拟题说明中部分连接条件已经准备好，答题时先验证，按缺失处补齐即可。

### 配置选项很多，我先按用途分组

你可能在完整配置样例里看到 `[defaults]`、`[inventory]`、`[privilege_escalation]`、`[ssh_connection]`、`[persistent_connection]`、`[selinux]`、`[colors]`、`[diff]` 等段落。它们分别管理通用默认值、清单、提权、SSH、连接复用、安全上下文、显示颜色和差异输出；旧资料还可能提到 Paramiko 或 accelerate 之类的历史配置。做第 1 题时只需写清单、角色/集合路径和连接提权等实际需要的项。`host_key_checking`、`log_path`、`ssh_args` 是常见排错或运维选项，是否启用要根据环境，而不是把整份模板复制进项目。

如果已经选中了 `all`，却只想对其中一部分测试，可以在命令上加 `--limit dev`；`--limit @retry.txt` 可从文件读取限制目标。这是执行时的额外筛选，不会修改 inventory。本套题里用它做小范围验证很方便，但最后仍要按题目要求对完整目标范围运行。

<!-- EXAM -->

**考试连接：**模拟题第 1 题会要求你建立 dev/test/prod/balancers/webservers 等组，并设置 role/collection 搜索路径。这题应该练到“零思考”。它不是一个孤立分值，而是后面所有 `hosts:` 的路由表。

<!-- EXERCISE -->

**随堂小测：**题目说“serverc、serverd 属于 prod；prod 又属于 webservers”。你会如何写 inventory？写完用什么命令确认 webservers 里确实有两台？

<details markdown="1"><summary>参考答案</summary>

```
[prod]
serverc
serverd

[webservers:children]
prod

ansible webservers --list-hosts
```

</details>

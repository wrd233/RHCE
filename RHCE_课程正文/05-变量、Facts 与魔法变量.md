# 变量、Facts 与魔法变量

这章是 RHCE 从“照着模块写”迈向“同一份 Playbook 管很多不同机器”的关键。你要学的不是变量语法本身，而是数据到底从哪里来。

变量的本质很简单：把会变化、会复用、或者不应该硬编码在 task 里的值抽出来。变量名通常遵循这些规则：字母、数字、下划线组成；大小写区分；建议字母开头；避免和 Ansible 的内部/保留变量冲突。这里“不能以 ansible 开头”更适合作为安全约定理解，而不是把它当成 YAML 解析器绝对禁止规则——你真正要避免的是覆盖已有的 `ansible_*` facts、连接变量或 magic variable。

### debug：学习变量最重要的显微镜

`debug` 有两个最常用入口：`var:` 直接查看变量对象；`msg:` 输出经过 Jinja2 渲染的字符串。学习变量、facts、register 时，不要靠猜，随手 debug。

```
- debug:
    var: ansible_devices

- debug:
    msg: "{{ inventory_hostname }} -> {{ ansible_default_ipv4.address }}"
```

### 变量来源一：Inventory 中的 host/group vars

主机变量只对该 host 生效，组变量对组成员生效；如果同一个变量在不同层级冲突，会进入 Ansible 的变量优先级体系。在这里，主机变量通常覆盖对应组变量，但完整优先级非常长，考试没必要整张背。你要做的是尽量不要在多个地方故意定义同名变量。

Inventory 里还有一类很特殊的 `ansible_*` 连接变量，例如 `ansible_host`、`ansible_port`、`ansible_user`、`ansible_become`、私钥路径等。它们不是业务数据，而是在告诉 Ansible“怎么连这个目标”。

### 变量来源二：Play 中 vars 与 vars\_files

`vars:` 适合少量、与 play 紧密相关的变量；嵌套字典可以用点号或下标访问。这里还要留意 play 的变量作用域：在一个 play 里定义的 vars，不应该想当然地认为下一个无关 play 一定能直接拿到。

`vars_files:` 把数据拆出去特别适合考试第 17 题：用户列表是一个文件，密码又在 Vault 加密变量文件中。Playbook 只表达逻辑，数据文件表达数据。这个分层比把几十个账号写死在 task 里稳得多。

### 变量来源三：命令行 extra vars

`-e` / `--extra-vars` 可以在运行时注入变量，而且优先级非常高。例如同一份部署 Playbook，通过 `-e "hosts=dev"` 与 `-e "hosts=prod"` 选择不同目标；前提是 Playbook 本身确实用 `hosts: "{{ hosts }}"` 引用了这个变量。备考里不一定高频，但它能帮你理解“Playbook 是程序骨架，变量是运行参数”。

### host\_vars / group\_vars：把 Inventory 数据项目化

Ansible 约定目录名是 **`host_vars` 与 `group_vars`**。文件名通常对应 inventory host/group；这样 inventory 就不必塞满 `key=value`，大型项目也更清晰。

### register：把“上一个 task 的结果”变成下一步数据

`register` 和模块同层级，它保存的是整个结果对象，不只是 stdout。命令模块常见字段有 `rc`、`stdout`、`stderr`、`changed`、`failed`。因此“先探测、再决定”是很自然的写法。

```
- name: check file
  command: test -f /opt/passwd
  register: status
  changed_when: false
  failed_when: false

- name: do something only when check succeeded
  debug:
    msg: ok
  when: status.rc == 0
```

不过后面你会学到更 Ansible 化的方式，例如 facts、`stat` 模块、条件测试；register 是通用机制，不代表每次探测都必须 shell。

### Facts：目标机器自己“告诉你它是谁”

这是本章最重要的部分。默认 play 会有 gathering facts 阶段，Ansible 收集目标主机的操作系统、内存、CPU、网络、块设备等信息。传统写法里你经常看到 `ansible_memtotal_mb`、`ansible_bios_version`、`ansible_devices`；现代形式也可以从 `ansible_facts` 字典访问。

你可以关闭自动收集 `gather_facts: false`，也可以在 task 中手动调用 `setup`。考试里如果不知道某个 fact 叫什么，最可靠的办法不是背答案，而是现场查询：

```
ansible servera -m setup
ansible servera -m setup -a 'filter=ansible_*_mb'
ansible servera -m setup -a 'filter=ansible_devices'
```

第 15 题“硬件报告”就是典型 facts 题：主机名、内存、BIOS、vda/vdb 大小都来自 facts。你要练到看到“目标主机自身信息”就自然想到 facts。

### set\_fact：在运行过程中合成新的变量

它适合把多个原始数据组合成一个后续好用的值，例如 `os_version: "{{ ansible_distribution }} {{ ansible_distribution_major_version }}"`。它和普通 vars 的区别在于：它是在 task 执行过程中为当前 host 设置 fact-like 变量。

### lookup：从控制端/执行环境读取外部数据

常见 lookup 有 env、file、pipe 三种。我们把语法写精确一点：

```
{{ lookup('env', 'PWD') }}
{{ lookup('file', '/etc/passwd') }}
{{ lookup('pipe', 'echo huawei') }}
```

它表达的思想很重要：有些数据并不来自受管节点，而来自**运行 Ansible 的控制上下文**。Navigator 下这个“控制上下文”可能是 execution environment，所以路径和可见文件要按实际环境理解。

### 自定义 local facts

我们也可以在受管节点 `/etc/ansible/facts.d/*.fact` 定义自己的事实，最终出现在 local facts（常见访问路径 `ansible_local` / `ansible_facts.ansible_local`）中。这个能力让你把“这个节点特有的业务标签”也变成 facts。RHCE 模拟题里不是主角，但它能帮你理解 facts 并不只来自操作系统探测。

### Magic Variables：不是主机事实，而是 Ansible 执行上下文

| 变量 | 你可以这样理解 | 考试常见用途 |
| --- | --- | --- |
| `inventory_hostname` | 当前目标在 inventory 里的名字 | 写报告、按主机名判断 |
| `ansible_hostname` | 从目标系统 fact 得到的主机名 | 和 inventory 名称区分 |
| `groups` | inventory 中“组 → 成员列表”的总字典 | Jinja2 循环所有主机 |
| `group_names` | 当前 host 属于哪些组 | 第 13 题按 dev/test/prod 分支 |
| `hostvars` | 从一个 host 去取另一个 inventory host 的变量/facts | 第 12 题生成包含所有主机的 hosts 文件 |

先判断数据来源，题目就简单一半：题目给的固定值适合 `vars`，外部 YAML 由 `vars_files` 引入，目标机信息来自 Facts，上个任务结果来自 `register`，清单关系可从 Magic Variables 取到，控制端数据可用 lookup 读取。

### 把变量的四个来源放在同一张图里

我们把一次自动化的数据按来源分开，就不容易在第 12、15、17 题里混淆。题目给定的用户列表来自变量文件；某台主机自己的内存和磁盘来自 Facts；`inventory_hostname`、`groups`、`hostvars` 描述当前执行和清单关系；上一任务的执行结果由 `register` 保存。**先问“这个值从哪里来”，再问“语法怎么写”。**

```yaml
- hosts: all
  gather_facts: true
  tasks:
    - name: See the four kinds of data
      ansible.builtin.debug:
        msg: >-
          {{ inventory_hostname }} has {{ ansible_memtotal_mb }} MB;
          groups={{ group_names }};
          distribution={{ ansible_distribution }}
```

运行之前用 `ansible all -m ansible.builtin.setup -a 'filter=ansible_devices'` 看设备数据的实际结构。磁盘不存在时，不能直接访问 `ansible_devices.vdb.size`；先用 `is defined` 或 `default('NONE')` 兜底。第 15 题要求的硬件报告包括主机名、内存 MB、BIOS 版本与 vda/vdb 大小，最终文件的 `key=value` 格式也要与下载的空模板一致。

### 用第 12 题理解 hostvars

第 12 题只在 dev 主机上生成 `/etc/myhosts`，但文件内容要列出所有清单主机。因此模板中循环 `groups['all']`，再用 `hostvars[host]` 读取每台主机的 Facts。`groups` 解决“有哪些主机”，`hostvars` 解决“这台主机有什么值”。模板里写 `hostvars[host].ansible_default_ipv4.address` 时，要先保证相关主机的 Facts 已收集；可以在前一个面向 all 的 play 执行 fact gathering，再在 dev play 渲染。

`ansible_default_ipv4.address` 通常比照抄某个 `ansible_eth0` 网卡名更适合做通用示例，因为网卡名会因环境变化。仍要用 `setup` 验证这套实验中的实际地址；模拟题文本甚至出现过 `172.25.254.*` 与验证输出 `172.25.250.*` 的不一致，不能把答案页中的某个 IP 当作事实。

### 变量冲突时先减少来源

变量优先级规则可以很长，但本套模拟练习最需要的是可解释性：清单放连接和分组信息，`vars_files` 放任务数据，Vault 放秘密，Facts 描述主机，`register` 放执行结果。若同名变量在多个位置重定义，先用 `debug: var=变量名` 确认实际值，再消除不必要的重复定义。高优先级的 `-e` 可以临时覆盖，但它不会自动写进评分时重新运行的命令，所以交付文件本身仍应自足。

### 再走两个小例子，把“变量是数据”落下来

第一个例子是外部变量文件。假设 `user_vars.yml` 中的 `users` 是一个字典，包含 `bjones` 的 `first_name: Bob`、`acook` 的 `home_dirs: /users/acook`；Playbook 用 `vars_files: [user_vars.yml]` 引入后，可以写 `users.bjones.first_name`，也可以写 `users['acook']['home_dirs']`。若用户名保存在变量 `flag` 中，就用 `users[flag]['first_name']`，这里的 `flag` 不加引号，因为它本身要先求值。项目规模大时，再把按主机或组变化的数据放进 `host_vars/`、`group_vars/`。

第二个例子是本地 Facts。在受管节点 `/etc/ansible/facts.d/custom.fact` 写 INI 内容：`[general]`、`package=httpd`、`service=httpd`、`state=started`。收集 Facts 后，我们就能从 `ansible_local.custom.general.package` 取包名，再交给 `dnf` 模块。这个例子说明 Facts 不只来自硬件探测，也可以由节点上的受管理数据提供。安装 `.fact` 文件后要重新收集 Facts，才会看到新值。

```ini
[general]
package=httpd
service=httpd
state=started
```

`lookup('file', '/path/key.pub')` 读取控制端文件，`lookup('pipe', 'date +%Y%m%d')` 获取控制端命令输出，`lookup('env', 'JAVA_HOME')` 读取控制端环境变量。它们和在远端运行 `command` 后 `register` 的区别很重要：一个从执行器所在环境取值，一个从受管节点取值。`ansible all -m setup --tree /tmp/facts` 还能把每台主机的 Facts 分开保存，适合研究数据结构；在 Navigator 中仍要确认这个路径对 EE 可见。

<!-- EXAM -->

**考试连接：**第 12、13、15、17 题都靠这章。特别是第 17 题：用户列表来自外部文件、密码来自 Vault、循环每个 user、根据 `item.job` 用 when 分类、再对不同 hosts 创建。你如果只背 user 模块，这题还是做不出来；真正的核心是“数据流”。

<!-- EXERCISE -->

**随堂小测：**“生成 /etc/myhosts，里面要包含 inventory 所有主机的 IP、FQDN、短主机名。”这句话涉及哪三个数据工具？

<details markdown="1"><summary>答案</summary>

`groups.all` 用来列出所有 inventory hosts；`hostvars[host]` 用来访问每个 host 的变量/facts；具体 IP/FQDN/hostname 来自 facts。然后通过 Jinja2 for 循环渲染。

</details>

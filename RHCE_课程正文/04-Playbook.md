# Playbook

到这里开始，Ansible 从“会发一条远程命令”变成“能把一项工作完整描述下来”。Playbook 是 RHCE 的主体，所以这里要把结构看得比模块参数更重要。

Playbook 是 YAML 文件，一份文件可以有多个 play；一个 play 面向一组目标主机，里面按顺序执行多个 task。一个 task 通常调用一个模块。变量、条件、循环、handler 这些能力都围绕这条基本结构展开。

我们把结构想成三层：Playbook 是 play 列表；每个 play 选定 `hosts`，并容纳变量、任务和 handler；每个 task 再调用模块并传入参数。后面所有新语法都要放回这三层去理解。

### YAML：不是难，主要是“层级必须看得出来”

写 YAML 时先守住三件事：大小写区分；空格表达层级；不要用 Tab 缩进。再加一条实战经验：同层级保持统一缩进，常见用 2 个空格。YAML 里你会反复见到三种数据类型：标量（一个值）、列表（`-` 开头的一组有序元素）、字典（`key: value`）。Playbook 之所以看起来复杂，只是这三种结构在嵌套。

```
- name: create users
  hosts: all
  tasks:
    - name: create lisi
      ansible.builtin.user:
        name: lisi
        state: present
```

读的时候从缩进读：最外层 `- name` 是一个 play；`tasks:` 下面是任务列表；每个任务是一个字典；`user:` 下面又是模块参数字典。

### 一个 play 的四个“区域”

我们可以把一个 play 拆成 target、vars、tasks、handlers 四个区域。你可以把它理解成：**我要在哪做（target）→ 我拿什么数据做（vars）→ 我要依次做什么（tasks）→ 哪些变更发生后要在结尾补做动作（handlers）。**

target 区域除了 `hosts`，还可以出现 `become`、`gather_facts`、`force_handlers` 等 play 级配置；vars 可以直接定义，也可以用 `vars_files` 引外部文件；tasks 是主体；handlers 是被 notify 触发的特殊任务。

### Multi-play：同一份文件里不同目标做不同事

设想我们先为 all 配仓库、装 httpd，再分别给 node1 和 node2 放不同的首页。它在教你一个很重要的拆分方式：**如果目标主机集合不同，就不必硬塞进一个 task + 一大串 when；可以直接拆成多个 play。**考试里第 3 题和第 9 题都很适合用 multi-play。

我们把这个课堂案例真正写出来。假设两台节点都已经把 RHEL 安装介质挂载到 `/media`，且里面有 `BaseOS`、`AppStream`；`node1`、`node2` 也已经在 inventory 中。第一个 play 完成公共准备，后两个 play 只负责各自的首页。如果安装介质没有挂载，`file:///media/...` 不会因为 YAML 写对了就自动可用。

```yaml
---
- name: Prepare both web servers
  hosts: node1:node2
  become: true
  tasks:
    - name: Configure BaseOS repository
      ansible.builtin.yum_repository:
        file: dvd
        name: baseos
        description: RHEL BaseOS from local media
        baseurl: file:///media/BaseOS
        gpgcheck: false
        enabled: true
    - name: Configure AppStream repository
      ansible.builtin.yum_repository:
        file: dvd
        name: appstream
        description: RHEL AppStream from local media
        baseurl: file:///media/AppStream
        gpgcheck: false
        enabled: true
    - name: Install Apache
      ansible.builtin.dnf:
        name: httpd
        state: present
    - name: Start Apache now and at boot
      ansible.builtin.service:
        name: httpd
        state: started
        enabled: true

- name: Publish node1 homepage
  hosts: node1
  become: true
  tasks:
    - name: Set homepage content
      ansible.builtin.copy:
        content: "node1\n"
        dest: /var/www/html/index.html

- name: Publish node2 homepage
  hosts: node2
  become: true
  tasks:
    - name: Set homepage content
      ansible.builtin.copy:
        content: "node2\n"
        dest: /var/www/html/index.html
```

保存成 `play2.yml` 后，先做 `ansible-playbook play2.yml --syntax-check`，再用 `--list-hosts` 核对三段 play 的目标；运行后从控制节点分别 `curl http://node1/` 与 `curl http://node2/`。如果连接被防火墙拦住，我们按题目要求放行 HTTP 服务；如果 SELinux 报错，先查目标文件的上下文。搭实验环境时要注意：清空已有仓库文件、停用 firewalld 或临时关闭 SELinux 可能使演示很快跑通，却会掩盖真实配置问题；交付时我们围绕明确的目标状态配置和验证。

再看另一个课堂例子：初始化 `demo` 账户，指定 UID `3450`、家目录 `/tmp/demo`、shell `/bin/bash`，配置 sudo 与 SSH 公钥。它说明“一个需求往往要拆成多个模块任务”，其中密码不能写成 `user.password: demo` 这样的明文；用户模块要接收目标系统适用的哈希。sudo 可放在 `/etc/sudoers.d/demo` 独立文件并用 `visudo -cf %s` 校验，公钥交给 `authorized_key` 模块。考试第 16 题的账户题会复用这条拆解思路。

```yaml
---
- name: Prepare demo account on lab nodes
  hosts: all
  become: true
  tasks:
    - name: Create the account
      ansible.builtin.user:
        name: demo
        uid: 3450
        home: /tmp/demo
        shell: /bin/bash
        password: "{{ demo_password_hash }}"
        state: present
    - name: Grant passwordless sudo for this lab account
      ansible.builtin.copy:
        content: "demo ALL=(ALL) NOPASSWD:ALL\n"
        dest: /etc/sudoers.d/demo
        mode: '0440'
        validate: 'visudo -cf %s'
    - name: Authorize the control node public key
      ansible.posix.authorized_key:
        user: demo
        key: "{{ lookup('file', '/home/devops/.ssh/id_rsa.pub') }}"
        state: present
```

这里的 `demo_password_hash` 要预先从加密变量文件或 Vault 提供；公钥路径也要换成控制节点上实际存在的文件。`authorized_key` 会维护正确的 `authorized_keys` 内容，不需要手工拼 `.ssh` 目录。这个例子只适合题目明确要求初始化账户并授予该 sudo 权限的实验环境；做模拟题时仍按题面要求的账户、密码与授权范围写。

### 失败以后到底会发生什么？

任务失败要按主机分别看：正常线性策略下，一个 host 在某个 task 失败后会退出当前 play 的后续普通任务，但其他 host 可以继续。

`ignore_errors: yes` 可以让失败被忽略；有时你会看到 shell 命令末尾 `|| true`。后者只是把 shell 的退出码硬变成成功，容易掩盖真实错误，所以考试里除非你很清楚为什么，否则更推荐用模块本身、`failed_when`、block/rescue 等 Ansible 方式表达。

### Handler：它不是“另一个 tasks”，而是“变更后的延迟动作”

典型场景是配置文件发生 changed 才 reload/restart 服务。task 用 `notify` 发通知，handler 在一个 play 的任务基本执行完后统一处理。这样你有 5 个 task 都改配置，也不会每改一次就重启一次服务。

```
tasks:
  - name: deploy httpd config
    template:
      src: httpd.conf.j2
      dest: /etc/httpd/conf/httpd.conf
    notify: restart httpd

handlers:
  - name: restart httpd
    service:
      name: httpd
      state: restarted
```

`listen` 允许多个 handler 监听同一个通知名称，这样一个 notify 可以触发一组动作。`force_handlers: yes` 则用于“已经被通知的 handler，即使后续普通 task 失败，也尽量在 play 结束时执行”。前提仍然是触发源真的产生了 changed。

**一个很重要的本质：**Handler 之所以好用，是因为它依赖 changed 语义。换句话说，Ansible 不只是“命令跑没跑”，还在追踪“系统状态有没有发生改变”。这也是幂等性、handler、评分重放为什么能串成一条线。

### 从一段可运行的任务理解 YAML

我们用第 3 题的两个目标集合看 Playbook 的层级。最外层的两个 `-` 表示两个 play；每个 play 的 `tasks` 又是列表。`name` 只是方便读日志，真正改变系统的是模块。第一段面向三个组，第二段只面向 dev，这比把主机判断塞进每个 task 更容易读。

```yaml
---
- name: Install application packages
  hosts: dev:test:prod
  become: true
  tasks:
    - name: Install PHP and MariaDB
      ansible.builtin.dnf:
        name:
          - php
          - mariadb
        state: present

- name: Install development tools
  hosts: dev
  become: true
  tasks:
    - name: Install package group
      ansible.builtin.dnf:
        name: '@Development Tools'
        state: present
```

在模拟题里可以继续加第三个 dev play，用 `name: '*'`、`state: latest` 更新包。实际执行前先 `ansible-playbook packages.yml --syntax-check`，再 `--list-hosts` 看目标，最后运行并检查包状态。`--check` 是预测模式，某些任务无法完整模拟；它适合辅助检查，不能代替真实运行和目标机验收。

### Handler 的触发条件是 changed

假设我们把 httpd 配置放在 `templates/httpd.conf.j2`。`template` 只有在目标文件内容变化时返回 changed，随后 `notify` 才通知 handler；handler 在本轮任务结束时统一重启服务。再运行一次，如果文件不变，handler 就不该重复执行。这是考试里“可重放”最直观的演示。

```yaml
tasks:
  - name: Render httpd configuration
    ansible.builtin.template:
      src: httpd.conf.j2
      dest: /etc/httpd/conf/httpd.conf
    notify: Restart httpd
handlers:
  - name: Restart httpd
    ansible.builtin.service:
      name: httpd
      state: restarted
```

<!-- EXAM -->

**考试连接：**你写任何题都先写最小骨架：`- hosts → tasks → module`。如果题目对象很多，再考虑 multi-play、loop、when、role。先让结构正确，再填参数，能明显降低 YAML 缩进错误。

<!-- EXERCISE -->

**随堂小练习：**“在 webservers 部署配置文件，如果文件内容真的改变了才重启 httpd。”这句话里，哪个 task 应该 notify？handler 应该做什么？

<details markdown="1"><summary>答案</summary>

负责 template/copy 配置文件的 task 加 `notify: restart httpd`；handler 使用 service/systemd 让 httpd restarted 或 reloaded。重点是“文件 changed 才触发”。

</details>

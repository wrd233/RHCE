# Ad-hoc 与常用模块

这一章看起来模块很多，容易产生“全都要背”的压迫感。其实你只需要建立“题目关键词 → 模块”的索引，然后学会现场查参数。

Ad-hoc 可以把它理解成“Ansible 的单行命令模式”：一次临时调用一个模块，适合检查、验证、做简单一次性操作。Playbook 则像可保存、可复跑、可组合控制流的脚本/配置。考试真正评分的主体通常是你保存下来的 playbook，但 ad-hoc 是非常好的**验证和排错工具**。

```
ansible 主机或组 -m 模块 -a '模块参数' [选项]
ansible all -m ping
ansible webservers -m shell -a 'rpm -q httpd'
```

### 先理解幂等性，再决定什么时候用 shell

命令执行模块不会自动替我们判断目标状态是否已满足。用一个例子看幂等性：如果你写 `shell: useradd lisi`，第二次跑可能失败；如果写 `user: name=lisi state=present`，第二次会发现目标状态已经满足，通常返回 ok。RHCE 的评分会重放 playbook，所以**优先选择描述状态的专用模块**，而不是把 RHCSA 命令原封不动塞进 shell。

不过也别把规则绝对化。`shell`/`command` 可以借助 `creates`、`removes` 或合适的 `changed_when` 做得更可控，但在考试里，如果有专用模块，优先专用模块通常最稳。

### command / shell / raw / script 怎么选

| 模块 | 你可以这样记 | 关键差异 |
| --- | --- | --- |
| `command` | 执行普通命令 | 不经过 shell 解释，因此管道、重定向等 shell 语法不能直接用。 |
| `shell` | 确实需要 `| > &&` 等 shell 能力 | 通过 shell 执行；更灵活，也更容易写出非幂等任务。 |
| `raw` | 连 Python 都没有的极简目标 | 绕过通常的模块执行路径，直接发送命令；常用于 bootstrap。 |
| `script` | 已有本地脚本，想在远端跑 | 更精确地说，Ansible 会把控制端脚本传到远端临时位置再执行；这点比“只读取脚本命令”更准确。 |

### 四种命令执行入口的边界

Ad-hoc 的基本形状是 `ansible 主机模式 -m 模块 -a '参数'`。默认的 `command` 直接执行程序，不经过 shell，所以管道、重定向和变量展开等 shell 功能要改用 `shell`；如果指令不依赖这些能力，`command` 更直观。`raw` 是更底层的远端命令通道，适合目标节点还没有可用 Python 的引导场景；它不像 `command`/`shell` 那样支持同样的 `chdir`、`creates`、`removes` 参数。`script` 则把控制端已有脚本传到远端执行，脚本源文件不必预先复制到节点。

```bash
ansible dev -m ansible.builtin.command -a 'uptime'
ansible dev -m ansible.builtin.shell -a 'df -h | tail -n 1'
ansible dev -m ansible.builtin.command -a 'chdir=/tmp creates=/tmp/done.marker touch done.marker'
ansible dev -m ansible.builtin.script -a './healthcheck.sh'
```

第三条只是说明参数：`creates` 指定的文件存在时不再执行命令。真实任务里更适合用 `file` 模块创建文件；而如果任务本质是执行脚本，`creates`/`removes` 能让它的重复运行更可控。试着把 `chdir` 写给 `raw`，就能看出一个坑：`raw` 不会按这个模块参数切目录，命令可能在远端默认工作目录运行。**看到任务结果成功，也要检查它把东西写到了哪里。**

### 文件对象：file / copy / fetch

`file` 管的是“文件对象状态”：存在、目录、touch、链接、权限、属主属组、删除。`copy` 管的是“把字节或内容放过去”；`fetch` 是“把远端普通文件拉回来”。这三个模块不要混成一个“文件模块”。

```
# 创建目录
ansible all -m file -a 'path=/opt/dir state=directory'

# 创建软链接
ansible node1 -m file -a 'src=/etc/passwd dest=/opt/passwd state=link'

# 控制端文件推送到远端
ansible all -m copy -a 'src=/etc/passwd dest=/tmp/ backup=true'

# 直接生成内容
ansible all -m copy -a 'content="httpd index\n" dest=/var/www/html/index.html'

# 拉回远端普通文件
ansible all -m fetch -a 'src=/etc/passwd dest=/opt/'
```

使用 `fetch flat=true` 时，如果 dest 是目录，末尾 `/` 很关键。还有一个考试思维：`file` 的 `path` 不是 shell glob，它不会像 `rm /tmp/*` 那样自动展开批量目标。批量对象应该用 loop，或者先用 find 取得列表。

### 软件仓库与软件包：yum\_repository + yum/dnf

`yum_repository` 把一个 repo stanza 变成模块参数：`name` 是仓库 ID，`description` 对应显示名称，`baseurl` 是地址，`enabled`/`gpgcheck`/`gpgkey` 对应仓库策略，`file` 决定写到哪个 `.repo` 文件。模拟题第 2 题几乎就是把题面字段逐项映射成这些参数。

`yum`（在新环境也常见 `dnf`）则负责包、包组和更新：`present` 安装、`latest` 更新、`absent` 卸载；包组可以写 `@Development Tools`。

### 服务：service 与 systemd

两者都能做启动、停止、重启、reload、enabled。`systemd` 还有 `daemon_reload`：当你改的是 systemd unit 本身时，systemd 需要重新加载 unit 定义。别把“改了任意服务配置文件”都机械地套 daemon-reload；只有 unit 配置发生变化才需要这一步，而像改 `httpd.conf` 通常是 reload/restart 服务。

### 用户与组：user / group

这两个模块基本就是把 RHCSA 的 `useradd/usermod/userdel` 和 `groupadd/groupmod/groupdel` 转成声明式参数。考试里真正容易错的不是 `name`，而是“附加组”“删除家目录”“密码需要哈希”等细节。第 17 题还会把它和 loop、when、Vault 组合起来。

### 计划任务：cron

minute/hour/day/month/weekday 决定时间，`job` 是命令，`user` 是运行身份，`state` 决定存在或删除。这里要记住一个好习惯：执行完用 `crontab -l -u USER` 验证最终系统状态。

### get\_url / unarchive / synchronize

`get_url` 是让受管节点自己下载 URL；`unarchive` 根据 `remote_src` 决定压缩包来自控制端还是远端；`synchronize` 本质上借助 rsync 做 push/pull。同步目录时，末尾斜杠决定了源目录本身是否包含在目标内：`src=/opt` 往往表达“把 opt 这个目录作为一个整体同步”，而 `src=/opt/` 表达“同步 opt 里面的内容”。这和 rsync 的语义一致。

我们先记一张“动词索引”：用户/组对应 `user`/`group`，软件包和仓库对应 `dnf`/`yum_repository`，服务对应 `service`，文件对象和内容对应 `file`/`copy`/`template`，下载和解压对应 `get_url`/`unarchive`，计划任务对应 `cron`。以后看到题面中的对象，我先从这里选择模块，再查参数。

参数忘了就查：

```
ansible-doc -s file
ansible-doc -s user
ansible-doc yum_repository
ansible-doc -l | grep -i firewall
```

### 把题目中的名词直接翻成任务

第 2 题要求每个受管节点拥有两个仓库。`name` 是仓库 ID，`description` 是描述，`baseurl` 指向 BaseOS/AppStream，`gpgcheck`、`gpgkey` 与 `enabled` 各自对应题面字段。我们先写一个仓库，另一个只替换 ID、描述和 URL；这样检查时更容易发现漏项。这里的 URL 只在这套练习环境有效。

```yaml
- name: Configure BaseOS repository
  ansible.builtin.yum_repository:
    name: rh294_BASE
    description: rh294 base software
    baseurl: http://content.example.com/rhel9.0/x86_64/dvd/BaseOS
    gpgcheck: true
    gpgkey: http://content.example.com/rhel9.0/x86_64/dvd/RPM-GPG-KEY-redhat-release
    enabled: true
    file: rhel_dvd
```

执行后我会看 `/etc/yum.repos.d/rhel_dvd.repo` 中是否真的有两个仓库段，再尝试 `dnf repolist`。`yum_repository` 的成功只说明文件状态符合预期；仓库地址是否能访问、元数据能否下载，还要另验。

第 3 题把包操作拆成三个目标集合：dev/test/prod 装 php 和 mariadb；仅 dev 装 `@Development Tools`；仅 dev 更新所有包。**目标集合不同，就分 play；对象相同、数据不同，可以用 loop。** 对于第 19 题，`cron` 模块把“每隔两分钟”写成 `minute: '*/2'`，`user: natasha` 指定执行身份，`job: echo hello` 是具体命令。交卷前用 `crontab -u natasha -l` 观察真正落下的任务。

### 一个文件题为什么可能需要五类模块

模拟题第 14 题看起来只要求 `/webdev/index.html`，其实验收入口是浏览器。我们要分开照顾目录的组和 `2775` 权限、页面文件、软链接、httpd 服务、防火墙与 SELinux 上下文。`mode: '2775'` 中开头的 2 是 SGID，允许新建文件继承目录组；`setype: httpd_sys_content_t` 让 Web 服务能读取页面。题面要求输出 `Development`，不要误写成 `Devlopment`。最终用 `curl http://servera.lab.example.com/webdev/` 验证网页，而不只看 Playbook 返回成功。

### 模块参数再细一层，避免只会认名字

`file` 的 `state: file` 只检查已有文件并可维护属性，不会凭空创建；`touch` 可创建空文件或更新时间戳；`directory`、`link`、`hard`、`absent` 分别对应目录、软链、硬链与删除。权限、属主和属组分别由 `mode`、`owner`、`group` 控制。`copy` 除了 `src`/`dest`，还可以用 `content` 直接生成文件，用 `backup` 保留被覆盖的旧文件，用 `remote_src: true` 表示源文件已经在受管节点。复制目录时，`src` 最后的 `/` 会改变复制的是目录本身还是目录中的内容，做题前最好拿临时目录试一下。

`fetch` 只拉取远端普通文件；默认在控制端按主机名分层保存，`flat: true` 才去掉这层目录结构。`get_url` 的 `url`、`dest` 决定从哪里下载到远端哪里，`owner/group/mode` 还能控制落盘属性。`unarchive` 用 `src`、`dest` 解压，`remote_src: true` 说明压缩包已经在受管节点或源地址可由受管节点访问；`creates` 可以给重复解压设置跳过条件。`synchronize` 通过 rsync 同步，`mode: push/pull` 决定方向，`delete` 会删除目标端多余文件，使用前必须清楚两端目录含义。

`user` 的 `uid`、`group`、`groups`、`shell`、`home`、`create_home`、`comment` 描述账户属性；`state: absent` 配合 `remove: true` 才会把家目录一并删除。`group` 用 `gid`、`name`、`state` 管组。`cron` 的 `minute/hour/day/month/weekday` 管时间，`name` 给任务稳定标识，`user` 指执行身份；如果用 `cron_file` 管系统级文件，参数要求要再查模块文档。用户模块的 `password` 需要系统认可的哈希，不能把明文口令直接写入该参数。

<!-- EXAM -->

**考试连接：**第 2、3、14、19 题直接大量使用本章模块；第 8 题自定义 role 也只是把这些模块搬进 `roles/apache/tasks/main.yml`。所以这一章的目标不是“背完模块”，而是看到题面后能 30 秒内列出模块清单。

<!-- EXERCISE -->

**随堂训练：**题目说“创建 /webdev，组为 devops，权限 2775，再建立 /var/www/html/webdev → /webdev 的软链接”。先不要写 YAML，只说需要几个 `file` task，它们各自的 `state` 是什么。

<details markdown="1"><summary>看答案</summary>

至少两个：目录 task 使用 `state: directory` 并设置 group/mode；软链接 task 使用 `state: link`，src 为 /webdev，dest 为 /var/www/html/webdev。

</details>

# Role 角色管理

Role 是“把一个完整 Playbook 项目按职责拆成标准目录”。真正重要的不是目录多，而是你以后知道某类东西应该放在哪里。

到了规模较大的项目：真正可复用的大型自动化很少是一份几百行 playbook 从头写到底，而是拆成 role。Role 让变量、tasks、handlers、模板、普通文件、元数据各归各位，然后用一个很短的 playbook 调用。

```text
roles/apache/
├── tasks/main.yml       主任务
├── handlers/main.yml    被 notify 的动作
├── templates/           Jinja2 模板
├── files/               普通静态文件
├── defaults/main.yml    可覆盖的默认变量
├── vars/main.yml        角色内部变量
├── meta/main.yml        角色元数据和依赖
├── README.md            使用说明
└── tests/               测试骨架
```

有了这棵树，你就不需要“背十个目录”，因为目录名基本就是内容类型。

### 创建 Role：先 init，再把原 Playbook 拆进去

```
ansible-galaxy role init apache
```

然后把原来 playbook 里的 tasks 放进 `tasks/main.yml`，handlers 放进 `handlers/main.yml`，模板放 templates，copy 的静态文件放 files。Role 内引用 template/file 时通常可以只写相对文件名，不用手工拼角色目录。

### 调用 Role：Playbook 会变得非常短

```
- name: use apache role
  hosts: webservers
  roles:
    - apache
```

`roles_path` 决定 Ansible 去哪里找角色。考试第 1 题要求你把这个路径配好，第 8/9 题才能顺利调用。

### defaults vs vars：不是“两个地方都能放变量”这么简单

`defaults` 的优先级比 `vars` 低。`defaults/main.yml` 更适合“这个角色给一个合理默认值，使用者可覆盖”；`vars/main.yml` 更像角色内部强约束。你在真实项目里希望角色可复用时，越希望外部定制的参数越应该倾向 defaults。

### Ansible Galaxy：既是命令，也是生态入口

Galaxy 提供 init、list、search、install、remove 等命令。考试里最常见的是两类：根据 requirements.yml 从 URL 安装角色；或者 `role init` 自己创建一个 role。不要把 Galaxy 理解成“只能联网下载公开角色”，它也可以从指定 tar.gz URL/文件安装。

### RHEL System Roles：考试里最省力也最容易“不会查”的部分

红帽提供的 system roles 已经把 timesync、SELinux 等复杂配置封装好了。你真正要做的是：找到角色 → 阅读 README → 确认变量名/结构 → 在 play 里设置 vars → roles 调用。这里千万别把变量名硬背成负担；`selinux_state` 和 timesync 变量的结构都可以从当前安装角色的 README 找到。

所以遇到 Role 题，我会先确认角色存在、读 README 找最小变量示例，再写 hosts/vars/roles，最后验证系统状态。

### 第 8 题：先写可工作的角色，再调用它

模拟题要求 `roles/apache`：安装并启用 httpd，启动 firewalld 并放行 HTTP，把 `templates/index.html.j2` 渲染成 `/var/www/html/index.html`。模板内容是 `Welcome to {{ ansible_fqdn }} on {{ ansible_default_ipv4.address }}`。我们先用 `ansible-galaxy role init roles/apache` 建结构，再把模块任务放进 `tasks/main.yml`；最后让 `newrole.yml` 面向 `webservers` 调用 `apache`。验收用 `curl serverc`、`curl serverd`，看到两台主机各自的 FQDN 和 IP。

我们现在把“拆进 Role”的动作走一遍。`tasks/main.yml` 放包、服务、防火墙和模板；模板发生变化时才通知 handler 重启 httpd。`firewalld` 是系统服务名，放行 HTTP 则交给 `ansible.posix.firewalld`；执行前用 `ansible-doc ansible.posix.firewalld` 确认当前环境提供该 collection。

```yaml
# roles/apache/tasks/main.yml
---
- name: Install httpd
  ansible.builtin.dnf:
    name: httpd
    state: present
- name: Start httpd
  ansible.builtin.service:
    name: httpd
    state: started
    enabled: true
- name: Start firewalld
  ansible.builtin.service:
    name: firewalld
    state: started
    enabled: true
- name: Allow HTTP through the firewall
  ansible.posix.firewalld:
    service: http
    permanent: true
    immediate: true
    state: enabled
- name: Publish the site homepage
  ansible.builtin.template:
    src: index.html.j2
    dest: /var/www/html/index.html
    mode: '0644'
  notify: Restart httpd
```

```yaml
# roles/apache/handlers/main.yml
---
- name: Restart httpd
  ansible.builtin.service:
    name: httpd
    state: restarted
```

```jinja2
Welcome to {{ ansible_fqdn }} on {{ ansible_default_ipv4.address }}
```

这是三个不同文件，不要把示例里写明的路径一股脑贴在同一文件里。因为模板引用目标机 Facts，调用 Role 的 play 要保持 `gather_facts` 开启。Role 的调用文件再写成下面这样，整个任务就从“一大段配置”变成了“这个组使用 apache 角色”。

```yaml
---
- name: Deploy Apache on the web servers
  hosts: webservers
  become: true
  roles:
    - apache
```

这里我把角色当成“一个负责交付完整结果的单元”。`tasks` 描述步骤，`templates` 放带变量的文件，`handlers` 放变更后的动作，`defaults` 放可覆盖的默认参数。学会这个目录映射后，第 8 题只是把第三章的模块和第九章的模板重新组织一下。

### 第 4、5、6、9 题是一条角色使用链

第 4、5 题使用系统已有的 Timesync/SELinux 角色。先安装或确认 `rhel-system-roles`，查看本机角色 README，再按当前版本的变量结构填写：Timesync 要指定 `classroom.example.com` 并启用适用的 NTP 参数；SELinux 要实现 `targeted`、`enforcing`。完成后用 `chronyc sources` 与 `getenforce` 验证目标状态。具体角色名、变量名要以现场安装的 README 为准；复制角色到项目目录是这套练习给出的做法，角色本来可见时不必机械复制。

第 6 题让我们用 `roles/requirements.yml` 从两个指定 tarball 安装 `balancer` 和 `phpinfo`；第 9 题再用两个 play 分别让 balancers 组调用 balancer、webservers 组调用 phpinfo。可以把它看成“先把工具放到可搜索路径，再在适合的主机组上调用”。写第 9 题时只需要两个有实际作用的 play；空的 `hosts: webservers` play 没有任务与角色，不会帮我们完成目标。验收除了运行输出，还要访问负载均衡入口和 `/hello.php`。

```yaml
# roles/requirements.yml
- name: balancer
  src: http://classroom.example.com/content/haproxy.tar.gz
- name: phpinfo
  src: http://classroom.example.com/content/phpinfo.tar.gz
```

`ansible-galaxy role install -r roles/requirements.yml -p roles/` 安装后，用 `ansible-galaxy role list -p roles/` 确认名称和路径。如果下载地址不可达，就先区分“练习资源没提供”与“Playbook 写错”，不要靠改角色名绕过题目。

### 角色内部任务多了怎么办

角色的 `tasks/main.yml` 可以用 `ansible.builtin.include_tasks` 引入其他任务文件，例如把安装步骤放 `install.yml`、配置步骤放 `configure.yml`。在角色调用前需要做准备任务，可以用 `pre_tasks`；角色执行后再做检查或收尾，可以用 `post_tasks`。这两项能帮助你读懂较大的项目，但本套模拟题的 apache 角色不需要为了“显得规范”强行拆成许多空文件。

```yaml
pre_tasks:
  - ansible.builtin.debug:
      msg: Preparing web servers
roles:
  - apache
post_tasks:
  - ansible.builtin.debug:
      msg: Apache role finished
```

Galaxy 的 `search`、`info`、`list`、`install`、`remove` 可以用于查找和管理角色；考试练习最要紧的是 `role init` 与按 requirements 安装。若角色来自指定 tarball，名称以 requirements 里的 `name` 为准，不要用压缩包文件名推断最终角色名。

<!-- EXAM -->

**考试连接：**第 4/5 题 system roles，第 6 题 Galaxy requirements，第 8 题自己创建 apache role，第 9 题调用 balancer/phpinfo。它们看起来是 6 道题，其实核心只有“Role 的目录/调用/安装/查 README”。

<!-- EXERCISE -->

**随堂问题：**Role 中 index.html.j2 放在哪里？如果是一个无需模板渲染的证书文件又放在哪里？

<details markdown="1"><summary>答案</summary>

Jinja2 模板放 `templates/`；普通静态文件放 `files/`。

</details>

# Jinja2 模板

Jinja2 是把“同一份配置骨架”渲染成“每台机器自己的最终文件”。它和 Facts、Variables、Magic Variables 连起来以后，很多综合题就突然顺了。

我们先这样定义：Jinja2 模板就是一个带变量、条件、循环的文本文件。它通常仍然长得像原配置文件，只是在那些每台机器不同的位置插入模板表达式。Ansible 在发送前渲染，再用 `template` 模块把最终文件放到目标节点。

**为什么不能用 copy：**`copy` 把内容当普通字节；`template` 会经过 Jinja2 引擎。模板里写了 `{{ ansible_default_ipv4.address }}` 却用 copy，远端看到的很可能就是这串大括号，而不是 IP。

### 变量表达式：`{{ ... }}`

```
Listen {{ ansible_ens160.ipv4.address }}:80
```

最值得理解的是“值从哪里来”。模板不是自己知道网卡地址，它只是引用了 play 执行时已经存在的 facts/vars。模板只是表现层。

### 条件：让一份模板适配不同硬件

```
{% if ansible_ens224 is defined %}
Listen {{ ansible_ens224.ipv4.address }}:80
{% elif ansible_ens160 is defined %}
Listen {{ ansible_ens160.ipv4.address }}:80
{% else %}
Listen 80
{% endif %}
```

这个例子很漂亮：优先 ens224，没有就 ens160，再没有就监听所有地址。你可以看到 when 是“决定 task 执不执行”，Jinja if 是“决定输出文件里渲染哪一段”。不要混。

### 循环：把 Inventory 展开成文本

模拟题第 12 题正是这个模型：

```
127.0.0.1 localhost localhost.localdomain
::1 localhost localhost.localdomain
{% for host in groups.all %}
{{ hostvars[host].ansible_default_ipv4.address }} {{ hostvars[host].ansible_fqdn }} {{ hostvars[host].ansible_hostname }}
{% endfor %}
```

`groups.all` 给你 host 名列表；`hostvars[host]` 把“正在循环到的 host 名”换成它的变量字典；facts 再给出 IP/FQDN/hostname。这一题本质上就是**Inventory 关系 + Facts 数据 + Jinja 循环**。

### 过滤器：对数据做最后一公里转换

先记三个常用过滤器：

| Filter | 用途 | 考试落点 |
| --- | --- | --- |
| `default('NONE')` | 变量/属性没有值时给默认值 | 硬件报告里 vdb 不存在时输出 NONE |
| `password_hash('sha512')` | 把明文密码转换为系统 user 模块所需哈希 | 创建用户题 |
| `dict2items` | 字典 → 可循环的 key/value 列表 | loop 字典 |

你不需要背一百个 filter。考试里看到“如果不存在给默认值”“需要密码哈希”“字典要 loop”，再想到这几个就够。

Template 的本质公式：模板骨架 → 变量 / Facts / Magic Vars → if / for / filters → 每台主机最终配置文件

### 让第 12 题的输出从数据中长出来

我们在控制节点保存 `hosts.j2`。前两行是题面固定的本机回环地址，后面循环所有清单主机。`hostvars[host]` 提供当前这台主机的事实；若某台主机没有收集 facts，模板可能失败，所以要先保证相关节点执行过 fact gathering。模板完成后，`template` 模块只需要在 dev 组的主机上把它放到 `/etc/myhosts`。

```jinja2
127.0.0.1 localhost localhost.localdomain localhost4 localhost4.localdomain4
::1 localhost localhost.localdomain localhost6 localhost6.localdomain6
{% for host in groups['all'] %}
{{ hostvars[host].ansible_default_ipv4.address }} {{ hostvars[host].ansible_fqdn }} {{ hostvars[host].ansible_hostname }}
{% endfor %}
```

题面示例与答案中的地址段并不完全一致，因此这里故意不硬编码 `172.25.*`；运行后用 `cat /etc/myhosts` 与各主机实际 facts 对照。`groups['all']` 的遍历顺序也不是评分重点，题目允许行顺序不同。

### 把 Jinja 的三种符号区分开

`{{ ... }}` 把值输出到文本；`{% if ... %}`、`{% for ... %}` 控制输出哪些行；`{# ... #}` 是不会进入最终文件的模板注释。`when` 控制整个 task 是否运行，模板内的 `if` 控制同一个 task 产生什么文本，这两个层次不要混。第 15 题的 `default('NONE')` 属于过滤器，用来为不存在的设备给出备用显示值；第 17 题的 `password_hash` 也属于过滤器，但涉及密码安全与重放稳定性，必须用实际环境验证。

模板渲染后最有说服力的验收是检查最终文件，而不是只看 `.j2` 源码。第 8 题首页应显示每台受管节点自己的 FQDN 与 IP，第 12 题 `/etc/myhosts` 应列全清单主机，第 15 题硬件报告应给缺失磁盘写 `NONE`。这三道题都在考“同一份文本骨架，根据不同主机数据产出不同文件”。

### 从 Redis 的单机配置过渡到代理配置

先设想 10 台 Redis 共用一份配置：固定的参数留在模板里，监听地址用 Facts 填充。最简单的 `bind {{ ansible_ens160.ipv4.address }} 127.0.0.1` 只适用于确实拥有 ens160 的主机；如果有的节点叫 bond0，模板应该用 `if/elif/else` 判断哪个事实存在。若某台是从节点，还可以在 `masterip is defined` 时输出 `slaveof {{ masterip }} {{ masterport | default(6379) }}`。这样一个模板就可以承载主从差异，但具体 Redis 配置指令仍要与当前软件版本核对。

再把视线移到 Nginx 代理：`groups['webserver']` 列出后端组，循环每个 host，从 `hostvars[host]` 取出对应地址，渲染成 `upstream` 中的多个 `server` 行。这里清单组叫 `webserver`，模板就必须同样查 `groups['webserver']`，并从网卡字典继续取 `.ipv4.address`，不能把整个字典当 IP 输出。这类错与 Jinja 语法本身无关，而是数据路径没对上。

过滤器的完整列表不必背，但要能按作用归类：`default` 给缺失值兜底，`upper/lower/trim` 整理字符串，`int/float/round` 转换数字，`length/first/last` 读取序列性质，`dict2items` 改变数据结构。课程中的 `default(omit)` 值得单独记：它让某个模块参数在变量不存在时被省略，而不是把字符串 `NONE` 传过去。这和第 15 题报告文件里要**显示** `NONE` 是两种不同需求。

### 过滤器可以分类理解，不需要逐个死记

字符串相关的 `upper`、`lower`、`capitalize`、`reverse`、`first`、`last`、`trim`、`center`、`length`、`list`、`shuffle`，解决大小写、截取、去空格、长度和排列问题。数字相关的 `int`、`float`、`abs`、`round`、`random`，解决类型转换、绝对值、舍入和随机取值；例如 `{{ '8' | int }}` 得到数字 8，`{{ 3.1415926 | round(2) }}` 得到两位小数。列表相关的 `length`、`min`、`max`、`sort`、`sum`、`flatten`、`join`、`union`、`intersect`、`difference`、`symmetric_difference` 则用于统计、排序、拉平嵌套列表和集合运算。

这些名字集中出现，是为了让我们知道“数据放进模板前可以转换”。针对当前模拟题，我会优先练 `default`、`dict2items`、`password_hash` 和主机 Facts 的引用；其他过滤器先建立用途索引，真的遇到要求再看文档。尤其是 `random` 和 `shuffle` 会引入随机性，不适合在要求稳定重放的配置文件中随意使用。

<!-- EXAM -->

**考试连接：**第 8 题自定义 apache role 的 index.html.j2、第 12 题 hosts.j2、第 15 题“缺失值 NONE”的 default 思维、第 17 题 password\_hash 都和这一章有关。

<!-- EXERCISE -->

**随堂练习：**如果 bastion 没有 vdb，但其他机器有，你想在报告中输出 `vdb_size=NONE`，为什么 `default` 比先写一个复杂 when 分支更自然？

<details markdown="1"><summary>答案</summary>

因为这是一个“取值失败时的默认表现”，而不是整项 task 是否执行的问题。把 fallback 放在表达式层最贴近需求。

</details>

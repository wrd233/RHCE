# Collection 集合

Collection 是为什么 RHCE 9 会出现“模块明明存在，但我这里找不到”的答案。把它理解成 Ansible 的插件/模块/角色发布包就够了。

Collection 源于 Ansible 生态增长：模块、插件、角色的开发速度和维护主体越来越多，不适合所有东西都绑在 ansible-core 的同一个版本里。于是核心执行引擎和可独立版本化的内容分离。

一个 Collection 可以包含 **modules、plugins、roles** 等内容。模块完整名称变成 `namespace.collection.module`，例如 `ansible.builtin.yum`、`community.general.parted`（具体模块归属以考试环境安装内容为准）。

### 为什么“安装位置”这么重要

下载成功不等于 Ansible 能找到。Ansible 会按配置的 collection 搜索路径加载内容。因此第 1 题先配置项目中的 collection 路径，第 7 题再把指定 tar.gz 装进去，是一整套逻辑。

```
ansible-galaxy collection install community.general
ansible-galaxy collection install ./community-general-6.3.0.tar.gz -p mycollections/
ansible-galaxy collection list
```

配置项在资料中可能出现 `collection_path` 或 `collections_path` 等写法。不同版本/资料写法容易让人焦虑，最稳的办法是考试环境里用 `ansible-config list | grep -i collection` 或提供的配置模板确认，不要凭记忆硬争单复数。

### FQCN 的意义

当两个 collection 都有同名 module 时，FQCN 能明确指定来源；同时你一眼能看出某个功能是不是 core 自带。看到 `ansible.builtin.xxx` 就知道它来自 builtin collection；看到其他 namespace，就应该意识到“需要对应 collection 可见”。

排查“模块找不到”：模块名写对？ → 属于哪个 Collection？ → Collection 装了吗？ → 装到配置搜索路径了吗？ → Navigator 的 EE 能看见吗？

### 第 7 题：安装位置与模块名一起验证

这套模拟练习要求把 `ansible-posix-1.5.1.tar.gz` 和 `community-general-6.3.0.tar.gz` 安装到 `/home/devops/ansible/mycollections`。Collection 在该目录下通常形成 `ansible_collections/命名空间/集合名` 的层级；第 1 题的 `collections_path` 必须能让执行器找到它。安装成功后，至少核对目录结构和 `ansible-galaxy collection list -p mycollections` 的结果，再用 `ansible-doc` 查一个将要使用的 FQCN。

```bash
ansible-galaxy collection install http://content.example.com/ansible-posix-1.5.1.tar.gz -p mycollections/
ansible-galaxy collection install http://content.example.com/community-general-6.3.0.tar.gz -p mycollections/
ansible-galaxy collection list -p mycollections/
```

第 10、11 题会用到存储相关模块。这里不要靠模块短名猜归属：在当前执行环境运行 `ansible-doc community.general.lvol`、`ansible-doc community.general.parted` 等命令，确认模块存在及参数。**安装 collection、配置搜索路径、在 Navigator 的 EE 中实际可见，是三个连续的检查。**宿主机 `ansible-doc` 能找到，不自动证明容器里的执行器也能找到。

<!-- EXAM -->

**考试连接：**第 7 题会给你 collection tar 包并要求装到指定 `mycollections`。它看起来像下载题，实际上是在考“内容包 + 搜索路径”这个模型。

<!-- EXERCISE -->

**随堂判断：**你已经把 collection tar.gz 下载到项目目录，但 `ansible-doc` 仍找不到里面的模块。最可能还缺什么？

<details markdown="1"><summary>答案</summary>

下载不等于安装。需要 `ansible-galaxy collection install ... -p 指定目录`，并保证 Ansible 的 collection 搜索路径能看到该目录。

</details>

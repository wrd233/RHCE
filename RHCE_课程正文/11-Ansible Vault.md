# Ansible Vault

Vault 解决的是“Playbook 需要秘密，但秘密又不能裸写在普通 YAML 里”。它不是密码管理系统的全部，只是 Ansible 数据文件的加密机制。

先记住一个事实：`ansible-vault` 可以对 Playbook、变量文件、模板等 Ansible 使用的数据文件进行加密。考试最常见的是加密变量文件，因为逻辑仍保持可读，而密码值被保护。

```
ansible-vault create secret.yml
ansible-vault encrypt locker.yml
ansible-vault view locker.yml
ansible-vault edit locker.yml
ansible-vault decrypt locker.yml
ansible-vault rekey salaries.yml
```

最重要的操作习惯是：**文件加密之后，不要用普通编辑器把密文当文本改。**使用 `ansible-vault edit`，或者明确 decrypt → 修改 → encrypt。普通编辑密文很容易破坏 Vault 格式。

### 密码文件：让 Playbook 非交互运行

模拟题要求 `/home/devops/ansible/secret.txt`，然后运行：

```
ansible-playbook --vault-password-file=secret.txt users.yml
```

这体现了考试评分的关键：系统可能自动重放你的 Playbook，所以不能依赖人工输入密码的交互过程。密码文件路径、权限、Playbook 是否真的能使用它，都是最终结果的一部分。

### rekey：不是“解密再重新加密”的手工流程

`ansible-vault rekey` 专门用于把现有 Vault 从旧密码迁移到新密码，并保持文件加密。模拟题第 18 题几乎就是命令识别题，别复杂化。

**本质上：**Vault 保护的是“静态文件里的秘密”。它并不会自动解决谁能读密码文件、运行时秘密如何审计等完整安全问题。考试范围内你先把 encrypt/view/edit/rekey/password-file 做稳。

### 第 16、17、18 题其实是一条秘密数据链

先在 `locker.yml` 中写 `pw_developer`、`pw_manager`，再按第 16 题指定的密码文件加密。密码文件与 Vault 文件承担不同职责：前者让 Ansible 获得解密凭据，后者保存受保护的数据。第 17 题用 `vars_files` 读取加密变量，再把明文密码交给 `password_hash('sha512')` 生成系统用户可用的哈希。运行 Playbook 时必须提供 `--vault-password-file secret.txt`，否则它连变量都读不开。

```text
user_list.yml 的 users ──→ loop 中的 item.name / item.job
locker.yml 的秘密     ──→ pw_developer / pw_manager
secret.txt 的口令      ──→ 解开 locker.yml
password_hash          ──→ 写入系统账户的密码哈希
```

按模拟题创建 `secret.txt` 后，应限制为当前用户可读，例如 `chmod 600 secret.txt`。`ansible-vault view --vault-password-file secret.txt locker.yml` 可以核对内容仍能解密；再检查文件开头是 Vault 格式，而不是裸露的 YAML。密码文件本身也是敏感内容，实际项目不应把它和仓库一起公开。

第 18 题是另一份现有加密文件 `salaries.yml` 的密钥轮换。用 `ansible-vault rekey`，提供旧密码和新密码，最后分别验证旧密码打不开、新密码能打开，且文件仍是加密状态。**rekey 只更换解密这份文件的口令，不会自动更新前面 `locker.yml` 所用的 `secret.txt`。** 两道题涉及的文件和口令要分开，不要误以为整个项目的 Vault 都统一换密钥。

<!-- EXAM -->

**考试连接：**第 16 题创建 Vault、第 17 题引用 Vault 变量并给用户生成 SHA512 哈希、第 18 题 rekey。三题连在一起学比拆开背快得多。

<!-- EXERCISE -->

**随堂小测：**locker.yml 已经加密，你突然想把 pw\_manager 改掉，最稳的命令是什么？

<details markdown="1"><summary>答案</summary>

`ansible-vault edit locker.yml`。不要直接 vim 密文。

</details>

"""Validate trainer answer archives before extracting into an empty VM directory."""
from pathlib import PurePosixPath


def validate_answers(archive):
    members={}
    for member in archive.getmembers():
        path=PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0]!='ansible':
            raise RuntimeError('答案归档包含越界路径，未覆盖任何文件')
        if path in members or not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise RuntimeError('答案归档包含重复路径或特殊文件，未覆盖任何文件')
        members[path]=member
    root=members.get(PurePosixPath('ansible'))
    if root is None or not root.isdir():
        raise RuntimeError('答案归档缺少普通 ansible 根目录')
    for path,member in members.items():
        # External leaf symlinks are valid student artifacts. Never allow an archive
        # member to be written through one while unpacking the rest of the archive.
        for parent in path.parents:
            if parent in members and not members[parent].isdir():
                raise RuntimeError('答案归档含经过链接或非目录的写入路径')
        if member.islnk():
            target=PurePosixPath(member.linkname)
            if target.is_absolute() or '..' in target.parts or target not in members or not members[target].isfile():
                raise RuntimeError('答案归档的硬链接目标不属于归档内普通文件')

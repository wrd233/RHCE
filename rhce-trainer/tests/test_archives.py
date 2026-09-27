import io
import tarfile
import unittest
from rhce_trainer.archives import validate_answers


class ArchiveTests(unittest.TestCase):
    def check(self,entries):
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w') as tar:
            for name,kind,target in [('ansible',tarfile.DIRTYPE,'')]+entries:
                item=tarfile.TarInfo(name);item.type=kind;item.linkname=target;tar.addfile(item)
        stream.seek(0)
        with tarfile.open(fileobj=stream) as archive:validate_answers(archive)

    def test_external_leaf_symlink_is_preserved(self):
        self.check([('ansible/roles',tarfile.SYMTYPE,'/usr/share/ansible/roles')])

    def test_member_cannot_write_through_symlink(self):
        with self.assertRaisesRegex(RuntimeError,'经过链接'):
            self.check([('ansible/link',tarfile.SYMTYPE,'/etc'),('ansible/link/passwd',tarfile.REGTYPE,'')])

    def test_external_hardlink_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'硬链接'):
            self.check([('ansible/secret',tarfile.LNKTYPE,'/etc/shadow')])

    def test_internal_hardlink_is_allowed(self):
        self.check([('ansible/one',tarfile.REGTYPE,''),('ansible/two',tarfile.LNKTYPE,'ansible/one')])

    def test_special_file_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'特殊文件'):
            self.check([('ansible/fifo',tarfile.FIFOTYPE,'')])

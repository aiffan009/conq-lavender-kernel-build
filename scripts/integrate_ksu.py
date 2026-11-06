"""Apply pinned KernelSU Next v1.0.9 manual hooks to the tested 4.4 tree."""
from pathlib import Path
import argparse,hashlib,json,zipfile,struct

KSU_COMMIT='2241696498ce9dd742ce80b52c3ed6cca26e03ea'
APK_SHA256='0013c41c9aeda2699f8a8af840839eb495f89bce7264b5c8fa42152b4c8d9a1e'
DAEMON_SHA256='85ca51266ae07b94393c13e139583c6d796d2530beb94ab187807445535203b7'

def integrate(kernel,ksu,manager,logs):
    logs.mkdir(parents=True,exist_ok=True)
    assert hashlib.sha256(manager.read_bytes()).hexdigest()==APK_SHA256
    with zipfile.ZipFile(manager) as z:daemon=z.read('lib/arm64-v8a/libksud_overlayfs.so')
    assert hashlib.sha256(daemon).hexdigest()==DAEMON_SHA256
    assert daemon[:5]==b'\x7fELF\x02' and struct.unpack_from('<H',daemon,18)[0]==183
    changes={}
    def edit(relative,before,after):
        path=kernel/relative;text=path.read_text()
        assert text.count(before)==1,(relative,text.count(before),before[:70])
        text=text.replace(before,after,1);path.write_text(text)
        changes[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    def hook(relative,signature,locals_text,declarations,body):
        anchor=signature+'\n{\n'+locals_text
        replacement=('#ifdef CONFIG_KSU\n'+declarations+'\n#endif\n'+signature+'\n{\n'+locals_text+'\n#ifdef CONFIG_KSU\n'+body+'\n#endif\n')
        edit(relative,anchor,replacement)
    hook('fs/exec.c',
         'static int do_execveat_common(int fd, struct filename *filename,\n\t\t\t      struct user_arg_ptr argv,\n\t\t\t      struct user_arg_ptr envp,\n\t\t\t      int flags)',
         '\tchar *pathbuf = NULL;\n\tstruct linux_binprm *bprm;\n\tstruct file *file;\n\tstruct files_struct *displaced;\n\tint retval;\n',
         'extern int ksu_handle_execveat(int *fd, struct filename **filename_ptr,\n\t\t\t      void *argv, void *envp, int *flags);',
         '\tif (!IS_ERR(filename))\n\t\tksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);')
    hook('fs/open.c',
         'SYSCALL_DEFINE3(faccessat, int, dfd, const char __user *, filename, int, mode)',
         '\tconst struct cred *old_cred;\n\tstruct cred *override_cred;\n\tstruct path path;\n\tstruct inode *inode;\n\tstruct vfsmount *mnt;\n\tint res;\n\tunsigned int lookup_flags = LOOKUP_FOLLOW;\n',
         'extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user,\n\t\t\t      int *mode, int *flags);',
         '\tksu_handle_faccessat(&dfd, &filename, &mode, NULL);')
    hook('fs/stat.c',
         'int vfs_fstatat(int dfd, const char __user *filename, struct kstat *stat,\n\t\tint flag)',
         '\tstruct path path;\n\tint error = -EINVAL;\n\tunsigned int lookup_flags = 0;\n',
         'extern int ksu_handle_stat(int *dfd, const char __user **filename_user, int *flags);',
         '\tksu_handle_stat(&dfd, &filename, &flag);')
    hook('fs/read_write.c',
         'ssize_t vfs_read(struct file *file, char __user *buf, size_t count, loff_t *pos)',
         '\tssize_t ret;\n',
         'extern bool ksu_vfs_read_hook;\nextern int ksu_handle_vfs_read(struct file **file_ptr, char __user **buf_ptr,\n\t\t\t       size_t *count_ptr, loff_t **pos);',
         '\tif (unlikely(ksu_vfs_read_hook))\n\t\tksu_handle_vfs_read(&file, &buf, &count, &pos);')
    hook('drivers/input/input.c',
         'static void input_handle_event(struct input_dev *dev,\n\t\t\t       unsigned int type, unsigned int code, int value)',
         '\tint disposition;\n',
         'extern bool ksu_input_hook;\nextern int ksu_handle_input_handle_event(unsigned int *type, unsigned int *code,\n\t\t\t\t int *value);',
         '\tif (unlikely(ksu_input_hook))\n\t\tksu_handle_input_handle_event(&type, &code, &value);')
    hook('fs/devpts/inode.c',
         'void *devpts_get_priv(struct inode *pts_inode)',
         '\tstruct dentry *dentry;\n\tvoid *priv = NULL;\n',
         'extern int ksu_handle_devpts(struct inode *inode);',
         '\tksu_handle_devpts(pts_inode);')
    # Built-in LSM hooks in this KSU tag supply prctl, setuid, rename and inode
    # permission hooks. Do not add duplicate LSM calls in security/security.c.
    makefile=kernel/'drivers/Makefile';text=makefile.read_text()
    assert 'CONFIG_KSU' not in text
    makefile.write_text(text+'\nobj-$(CONFIG_KSU) += kernelsu/\n')
    kconfig=kernel/'drivers/Kconfig';text=kconfig.read_text()
    assert 'drivers/kernelsu/Kconfig' not in text
    kconfig.write_text(text+'\nsource "drivers/kernelsu/Kconfig"\n')
    link=kernel/'drivers/kernelsu';assert not link.exists()
    link.symlink_to(ksu/'kernel',target_is_directory=True)
    # A source archive has no Git history. Pin the version corresponding to
    # the exact upstream v1.0.9 release, instead of upstream's fallback 11998.
    mk=ksu/'kernel/Makefile';text=mk.read_text()
    assert text.count('ccflags-y += -DKSU_VERSION=11998')==1
    mk.write_text(text.replace('ccflags-y += -DKSU_VERSION=11998','ccflags-y += -DKSU_VERSION=12797'))
    embedded=ksu/'kernel/embed_ksud.c'
    with embedded.open('w') as f:
        f.write('/* Official ARM64 OverlayFS ksud from KernelSU Next v1.0.9. */\n')
        f.write('unsigned int ksud_size = '+str(len(daemon))+';\nconst char ksud[] = {\n')
        for i in range(0,len(daemon),24):f.write(','.join('0x%02x'%b for b in daemon[i:i+24])+',\n')
        f.write('};\n')
    report={'kernelsu_commit':KSU_COMMIT,'kernelsu_version':12797,'hooks':'manual; built-in LSM hooks; no KSU kprobe hooks','manager_cert_size':998,'manager_cert_sha256':'79e590113c4c4c0c222978e413a5faa801666957b1212a328e46c00c69821bf7','official_manager_apk_sha256':APK_SHA256,'embedded_daemon_sha256':DAEMON_SHA256,'embedded_daemon_size':len(daemon),'manual_hook_file_sha256':changes,'kernel_namespace_note':'Upstream KernelSU v1.0.9 Makefile supplies its path_umount compatibility backport.'}
    (logs/'kernelsu-integration.json').write_text(json.dumps(report,indent=2))
    print('Applied six guarded manual hooks and embedded official ARM64 ksud.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--kernel',type=Path,required=True);p.add_argument('--ksu',type=Path,required=True);p.add_argument('--manager',type=Path,required=True);p.add_argument('--logs',type=Path,required=True)
    a=p.parse_args();integrate(a.kernel.resolve(),a.ksu.resolve(),a.manager.resolve(),a.logs.resolve())

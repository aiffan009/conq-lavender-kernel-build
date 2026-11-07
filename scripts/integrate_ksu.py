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
    # Linux 4.4 rejects init -> su when ksud lives on nosuid /data, even
    # with SELinux allow rules. Upstream KSU supplies a narrowly scoped
    # compatibility helper; wire it into the legacy SELinux check.
    edit('security/selinux/hooks.c',
         'static int check_nnp_nosuid(const struct linux_binprm *bprm,',
         '#ifdef CONFIG_KSU\n'
         'extern bool is_ksu_transition(const struct task_security_struct *old_tsec,\n'
         '\t\t\t      const struct task_security_struct *new_tsec);\n'
         '#endif\n\n'
         'static int check_nnp_nosuid(const struct linux_binprm *bprm,')
    edit('security/selinux/hooks.c',
         '\tif (new_tsec->sid == old_tsec->sid)\n\t\treturn 0; /* No change in credentials */',
         '\tif (new_tsec->sid == old_tsec->sid)\n\t\treturn 0; /* No change in credentials */\n\n'
         '#ifdef CONFIG_KSU\n'
         '\t/* Permit only the KSU init -> su boot-daemon transition. */\n'
         '\tif (is_ksu_transition(old_tsec, new_tsec)) {\n'
         '\t\tpr_info_once("KernelSU: legacy init -> su transition allowed\\n");\n'
         '\t\treturn 0;\n'
         '\t}\n'
         '#endif')
    # Before the policy is loaded, security_context_to_sid returns
    # SECINITSID_KERNEL for su. Never cache that temporary SID for later boot.
    ksud_source=ksu/'kernel/ksud.c';text=ksud_source.read_text()
    before=('\tstatic u32 ksu_sid;\n\tchar *secdata;\n\tu32 seclen;\n'
            '\tbool allowed = false;\n\n\tif (!ksu_sid)\n'
            '\t\tsecurity_secctx_to_secid("u:r:su:s0", strlen("u:r:su:s0"), &ksu_sid);')
    after=('\tu32 ksu_sid = 0;\n\tchar *secdata;\n\tu32 seclen;\n'
           '\tbool allowed = false;\n\n'
           '\tif (security_secctx_to_secid("u:r:su:s0", strlen("u:r:su:s0"), &ksu_sid))\n'
           '\t\treturn false;')
    assert text.count(before)==1,'upstream is_ksu_transition SID-cache anchor changed'
    ksud_source.write_text(text.replace(before,after,1))
    changes['KernelSU-Next/kernel/ksud.c']=hashlib.sha256(ksud_source.read_bytes()).hexdigest()
    # Backport before make starts. Upstream's Makefile-time sed insertion can
    # occur after fs/namespace.o has already been compiled by a parallel job.
    umount_backport='''#ifdef CONFIG_KSU
static int can_umount(const struct path *path, int flags)
{
\tstruct mount *mnt = real_mount(path->mnt);

\tif (flags & ~(MNT_FORCE | MNT_DETACH | MNT_EXPIRE | UMOUNT_NOFOLLOW))
\t\treturn -EINVAL;
\tif (!may_mount())
\t\treturn -EPERM;
\tif (path->dentry != path->mnt->mnt_root)
\t\treturn -EINVAL;
\tif (!check_mnt(mnt))
\t\treturn -EINVAL;
\tif (mnt->mnt.mnt_flags & MNT_LOCKED)
\t\treturn -EINVAL;
\tif (flags & MNT_FORCE && !capable(CAP_SYS_ADMIN))
\t\treturn -EPERM;
\treturn 0;
}

int path_umount(struct path *path, int flags)
{
\tstruct mount *mnt = real_mount(path->mnt);
\tint ret;

\tret = can_umount(path, flags);
\tif (!ret)
\t\tret = do_umount(mnt, flags);
\tdput(path->dentry);
\tmntput_no_expire(mnt);
\treturn ret;
}
#endif

'''
    edit('fs/namespace.c','static bool is_mnt_ns_file(struct dentry *dentry)',umount_backport+'static bool is_mnt_ns_file(struct dentry *dentry)')
    edit('fs/internal.h','extern void __init mnt_init(void);','extern void __init mnt_init(void);\n#ifdef CONFIG_KSU\nint path_umount(struct path *path, int flags);\n#endif')
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
    text=text.replace('ccflags-y += -DKSU_VERSION=11998','ccflags-y += -DKSU_VERSION=12797')
    start=text.index('ifneq ($(shell grep -Eq "^static int can_umount"')
    end=text.index('ccflags-y += -Wno-implicit-function-declaration',start)
    text=text[:start]+'# path_umount backport is applied by integrate_ksu.py before compilation.\n\n'+text[end:]
    mk.write_text(text)
    embedded=ksu/'kernel/embed_ksud.c'
    with embedded.open('w') as f:
        f.write('/* Official ARM64 OverlayFS ksud from KernelSU Next v1.0.9. */\n')
        f.write('unsigned int ksud_size = '+str(len(daemon))+';\nconst char ksud[] = {\n')
        for i in range(0,len(daemon),24):f.write(','.join('0x%02x'%b for b in daemon[i:i+24])+',\n')
        f.write('};\n')
    report={'kernelsu_commit':KSU_COMMIT,'kernelsu_version':12797,'hooks':'manual; built-in LSM hooks; no KSU kprobe hooks','manager_cert_size':998,'manager_cert_sha256':'79e590113c4c4c0c222978e413a5faa801666957b1212a328e46c00c69821bf7','official_manager_apk_sha256':APK_SHA256,'embedded_daemon_sha256':DAEMON_SHA256,'embedded_daemon_size':len(daemon),'manual_hook_file_sha256':changes,'kernel_namespace_note':'path_umount and can_umount plus internal prototype applied before compilation. Upstream Makefile-time namespace edits removed to prevent a parallel build race.'}
    report['legacy_selinux_note']='MODULEFIX2: call is_ksu_transition after normal fast paths and resolve su SID without caching pre-policy SECINITSID_KERNEL. Log first accepted init -> su transition. Other transitions retain original checks.'
    (logs/'kernelsu-integration.json').write_text(json.dumps(report,indent=2))
    print('Applied six guarded manual hooks, legacy SELinux boot-daemon transition, early path_umount backport, and official ARM64 ksud.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--kernel',type=Path,required=True);p.add_argument('--ksu',type=Path,required=True);p.add_argument('--manager',type=Path,required=True);p.add_argument('--logs',type=Path,required=True)
    a=p.parse_args();integrate(a.kernel.resolve(),a.ksu.resolve(),a.manager.resolve(),a.logs.resolve())

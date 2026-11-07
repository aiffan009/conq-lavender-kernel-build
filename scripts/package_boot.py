from pathlib import Path
import argparse,struct,hashlib,zlib,json,subprocess,sys,zipfile

ROOT=Path(__file__).resolve().parent.parent
def package(kernel,out,variant='baseline'):
    lock=json.loads((ROOT/'build-lock.json').read_text())
    with zipfile.ZipFile(ROOT/'fixtures/original-boot.zip') as z:base=z.read('boot.img')
    assert hashlib.sha256(base).hexdigest()==lock['original_boot_sha256']
    assert base[:8]==b'ANDROID!' and len(base)==67108864
    assert struct.unpack_from('<I',base,40)[0]==0
    assert struct.unpack_from('<I',base,16)[0]==0 and struct.unpack_from('<I',base,24)[0]==0
    payload=kernel.read_bytes();decoder=zlib.decompressobj(31)
    raw=decoder.decompress(payload)+decoder.flush();dtb=decoder.unused_data
    assert decoder.eof and raw[56:60]==b'ARMd'
    assert b'Linux version 4.4.285' in raw
    with_ksu=variant=='kernelsu-next'
    if with_ksu:
        assert b'KernelSU' in raw
        lock=dict(lock,stage='kernelsu_next_v1.0.9_manual_hooks_modulefix1',kernelsu_commit='2241696498ce9dd742ce80b52c3ed6cca26e03ea',kernelsu_version=12797,module_fix='legacy SELinux init -> su transition on nosuid data')
    assert dtb[:4]==b'\xd0\x0d\xfe\xed'
    assert struct.unpack_from('>I',dtb,4)[0]==len(dtb)
    page=struct.unpack_from('<I',base,36)[0];assert page==4096
    header=bytearray(base[:page]);struct.pack_into('<I',header,8,len(payload))
    ident=hashlib.sha1(payload+struct.pack('<I',len(payload))+struct.pack('<II',0,0)).digest()
    header[576:608]=ident+b'\0'*12
    out.mkdir(parents=True,exist_ok=True)
    boot=out/'boot.img';data=bytes(header)+payload
    boot.write_bytes(data.ljust(((len(data)+page-1)//page)*page,b'\0'))
    subprocess.run([sys.executable,str(ROOT/'scripts/avbtool.py'),'add_hash_footer','--image',str(boot),'--partition_name','boot','--partition_size',str(len(base)),'--algorithm','NONE','--salt','74f7b8fe6eb24d1613690cf8dcf66f6658da5a7d7cd8e9b50c09060dce28a2f6','--prop','com.android.build.boot.os_version:11','--prop','com.android.build.boot.security_patch:2021-08-05'],check=True)
    result=boot.read_bytes();assert len(result)==len(base)
    assert result[12:576]==base[12:576] and result[608:page]==base[608:page]
    assert result[page:page+len(payload)]==payload and result[576:596]==ident
    verify=subprocess.run([sys.executable,str(ROOT/'scripts/avbtool.py'),'verify_image','--image',str(boot)],capture_output=True,text=True)
    (out/'avb-verification.txt').write_text(verify.stdout+verify.stderr)
    assert verify.returncode==0,(verify.stdout,verify.stderr)
    boot_hash=hashlib.sha256(result).hexdigest()
    title='Conq 4.4 KernelSU Next 12797 MODULEFIX1 TEST' if with_ksu else 'Conq 4.4 BASELINE TEST - no KernelSU'
    script=(ROOT/'fixtures/recovery-installer.sh').read_text().replace('@TITLE@',title).replace('@SHA256@',boot_hash)
    archive=out/('Conq-4.4-KernelSU-Next-12797-MODULEFIX1-TEST.zip' if with_ksu else 'Conq-4.4-BASELINE-NO-KSU-TEST.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('META-INF/com/google/android/update-binary',script)
        z.writestr('META-INF/com/google/android/updater-script','# Recovery shell installer\n')
        z.writestr('boot.img',result)
        z.writestr('SOURCE.json',json.dumps(lock,indent=2))
        z.write(ROOT/'LICENSE-kernel.txt','LICENSE')
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    zip_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
    (out/(archive.name+'.sha256')).write_text(zip_hash+'  '+archive.name+'\n')
    (out/'build-manifest.json').write_text(json.dumps({'stage':lock['stage'],'kernelsu_integrated':with_ksu,'device_tested':False,'kernel_payload_sha256':hashlib.sha256(payload).hexdigest(),'dtb_sha256':hashlib.sha256(dtb).hexdigest(),'boot_sha256':boot_hash,'zip_sha256':zip_hash,'source':lock},indent=2))
    print('PACKAGED',archive)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--kernel',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--variant',choices=['baseline','kernelsu-next'],default='baseline')
    args=parser.parse_args();package(args.kernel,args.out.resolve(),args.variant)

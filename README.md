# Conq 4.4 kernel build — ขั้นแรก ยังไม่มี KernelSU

ชุดนี้ใช้ GitHub Actions เป็นเครื่อง Linux ชั่วคราว ไม่ต้องลง Linux บนคอมพิวเตอร์

## ลำดับงาน

1. Build ซอร์ส kernel 4.4 ที่พบ commit ตรงกับ Conq ด้วย config ที่ดึงจาก boot เดิม และ compiler Proton Clang ที่ใช้ LLVM commit ตรงกัน
2. ทดสอบว่าตัวที่ build ใหม่เปิด Conq ได้จริง
3. เมื่อข้อ 2 ผ่าน จึงรวม KernelSU Next แบบ non-GKI/manual hooks และ build รอบถัดไป

**ผลรอบแรกจะชื่อ `Conq-4.4-BASELINE-NO-KSU-TEST.zip` และตั้งใจยังไม่มี KernelSU** ถ้า baseline ยังไม่บูต ต้องแก้ความต่างของซอร์ส/config ก่อนเพิ่ม root

kernel เดิมมี `-dirty` จึงอาจมีส่วนแก้โค้ดที่ไม่ได้อยู่ใน public commit การพบ commit ตรงกันไม่ใช่หลักประกันว่าจะ build แล้วบูตได้ทันที

## อัปโหลดไฟล์และสั่ง build

1. สมัคร/ล็อกอิน GitHub และยืนยันอีเมลให้เรียบร้อย
2. สร้าง repository ใหม่ชื่อ `conq-lavender-kernel-build` เลือก **Public** หากยอมรับให้ไฟล์ build เหล่านี้เป็นสาธารณะ Standard Linux runner ของ public repository ไม่คิดค่า compute ตามเงื่อนไข GitHub หากเลือก Private ต้องตรวจโควตาบัญชีก่อน
3. แตก `Conq-4.4-GitHub-Build-Setup.zip` แล้วอัปโหลด **เนื้อหาข้างในทั้งหมด** ไปที่ root ของ repository โดยรักษาโครงสร้าง `.github/workflows/`, `scripts/`, `configs/`, `fixtures/` ไว้ อย่าอัปโหลด ZIP ชุด setup ทั้งก้อนเป็นไฟล์เดียว
4. หลังอัปโหลด ต้องเห็น `.github/workflows/build-baseline.yml` อยู่ใน repository ถ้ามองไม่เห็น workflow จะยังรันไม่ได้
5. ไปแท็บ **Actions → Conq 4.4 baseline - no KernelSU yet → Run workflow** แล้วเลือก branch หลัก
6. ถ้า build ผ่าน จะมี artifact ชื่อ `conq-4.4-baseline-...` ให้ดาวน์โหลดในหน้ารายการรัน แตก artifact จะพบ ZIP ทดสอบ, `boot.img`, checksum, manifest และ log
7. **อย่าแฟลช ZIP ชุด setup หรือ artifact wrapper ตรง ๆ** ไฟล์สำหรับแฟลชคือ `Conq-4.4-BASELINE-NO-KSU-TEST.zip` ข้างใน artifact เท่านั้น ให้ตรวจ log/manifest ก่อนทดสอบ
8. ถ้า build ไม่ผ่าน ส่งลิงก์ Actions หรือ log มาแก้ต่อได้ ไม่มีอิมเมจใหม่ที่ใช้แฟลชได้เพียงเพราะมี artifact ของ log ถูกอัปโหลด

## ขอบเขต

workflow รันเมื่อกดเองเท่านั้น จำกัดเวลา 90 นาที ไม่อัปโหลด ROM system/vendor หรือข้อมูลโทรศัพท์ส่วนตัว ไม่ใช้ token ส่วนตัว ไม่สร้าง release อัตโนมัติ artifact เก็บ 7 วัน

`fixtures/original-boot.zip` เป็น boot ของ Conq ต้นฉบับที่เก็บเป็นแม่แบบ ไฟล์นี้ไม่ใช่ kernel build ใหม่ `configs/conq-original.config` เป็น config ที่สกัดจาก kernel เดิม ตัว build ยังคง cmdline และ ramdisk ว่างแบบ Conq เดิม ใช้ kernel+DTB ที่คอมไพล์ใหม่และคำนวณ boot ID/AVB hash ใหม่

ชุดนี้ยังไม่เคยรัน compile บน Actions และยังไม่ใช่ kernel ที่ผ่านการทดสอบบนโทรศัพท์ การตรวจในเครื่อง Windows ทำได้เฉพาะ syntax และการสร้างแพ็กเกจโดยใช้ payload เดิม

เตรียม `Conq-OriginalBoot-RESTORE.zip` ที่ทดสอบคืน boot ได้แล้วไว้บนโทรศัพท์ก่อนทดสอบ baseline ไม่ต้องล้างข้อมูลเพื่อทดสอบ kernel

## แหล่งที่มา

- [ซอร์ส kernel commit ที่ตรง](https://github.com/stormbreaker-project/kernel_xiaomi_lavender/commit/46b4f3ea4a835fa6a1752d0608f36c9377c5094e)
- [Proton Clang commit](https://github.com/kdrag0n/proton-clang/commit/9fb011b183fe7e69b04b873ef6533b4b077e3c5e)
- [แนวทาง KernelSU Next สำหรับ non-GKI](https://kernelsu-next.github.io/webpage/pages/how-to-integrate-for-non-gki.html)
- [วิธีกด Run workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

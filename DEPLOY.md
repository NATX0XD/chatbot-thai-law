# ขึ้น Render

บอทตัวนี้ออกแบบมาให้อยู่ในเครื่อง 512 MB ได้ ซึ่งเป็นขนาดของ Render free plan พอดี
ค่าที่วัดจริงในคอนเทนเนอร์ที่จำกัดไว้ 512 MB คือ **peak 227 MB** และ **บูตเสร็จใน 0.7 วินาที**

---

## ทำไมต้องแก้ก่อนขึ้น

ของเดิมเสิร์ฟด้วย torch + BGE-M3 ในตัวโปรเซส กินราว 1.4 GB และใช้เวลาโหลดโมเดล ~30 วินาที
ซึ่งนานกว่าอายุ reply token ของ LINE (~30 วินาที) แปลว่าต่อให้ไม่ OOM ผู้ใช้ก็ไม่ได้รับคำตอบอยู่ดี
สามอย่างที่กินแรมถูกถอดออกทั้งหมด

| ของเดิม | แรม | ของใหม่ | แรม |
|---|---:|---|---:|
| torch + BGE-M3 ในโปรเซส | ~1,400 MB | เรียก BGE-M3 ตัวเดียวกันผ่าน API | ~0 MB |
| `bm25.pkl` (rank_bm25) | 202 MB | `bm25_compact.npz` (numpy postings) | 8 MB |
| `import pythainlp` | 266 MB | vendor เฉพาะ newmm | 82 MB |
| corpus เป็น dict 27,203 ตัว | 97 MB | อ่านตาม byte offset | 0.2 MB |
| vectors cast เป็น float32 | 111 MB | memory-map + คูณทีละบล็อก | ~56 MB |

**คุณภาพการค้นคืนไม่เปลี่ยน** เพราะ

- embedding เรียก **checkpoint เดียวกัน** (`BAAI/bge-m3`) ที่ใช้สร้าง `vectors.npy` จึงไม่ต้อง rebuild index
- BM25 compact ให้คะแนนต่างจากของเดิมแค่ 2.6e-06 (float32 rounding) และลำดับ top-30 ตรงกันทุก query
- tokenizer ที่ vendor มาให้ผลตรงกับ pythainlp บนตัวบทจริง 200 มาตราสุ่ม
- calibration เดิมยังได้ in-scope 14/14, off-topic รั่ว 0/5, missing-law รั่ว 0/5

---

## สิ่งที่ต้องมีก่อน

1. **บัญชี GitHub** — Render build image จาก git repo
2. **บัญชี Render** — https://dashboard.render.com
3. **บัญชี Cloudflare** (ฟรี ไม่ต้องผูกบัตร) — ใช้ Workers AI รัน `@cf/baai/bge-m3`
   ต้องเก็บมา 2 ค่า
   - **Account ID** — dash.cloudflare.com > Workers & Pages > แถบขวา
   - **API token** — dash.cloudflare.com/profile/api-tokens > Create Token
     สิทธิ์ `Account` > `Workers AI` > `Read`

   ฟรี **10,000 neurons/วัน** และ bge-m3 คิด 1,075 neurons ต่อ 1M input tokens
   = ราว **9.3M tokens/วัน** คำถามหนึ่งครั้งกิน ~40 tokens จึงได้ราว 230,000 คำถาม/วัน

   **DeepInfra ใช้ไม่ได้ถ้าไม่อยากเสียเงิน** ต้องผูกบัตรหรือเติมเงินก่อน ไม่งั้นได้ 402
   **SiliconFlow ใช้ไม่ได้** สมัครต้องใช้เบอร์โทรจีน
   **NVIDIA NIM ปิด bge-m3** ไปแล้วเมื่อ 24 ส.ค. 2026

---

## ขั้นตอน

### 1. ตรวจว่า embedding จากผู้ให้บริการตรงกับ index

ข้อนี้สำคัญที่สุดและต้องทำ **ก่อน** deploy ถ้าเจ้านั้นเสิร์ฟคนละ checkpoint
cosine จะเลื่อนหมด เกณฑ์ `min_dense_sim = 0.54` จะไม่ได้แปลว่าอะไรอีกต่อไป
และอาการจะออกมาเป็น "ตอบแย่ลง" เงียบ ๆ ไม่ใช่ error

```bash
cd ~/thai-law-bot
EMBED_API_KEY=<token> \
EMBED_BASE_URL=https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1 \
EMBED_API_MODEL='@cf/baai/bge-m3' \
.venv/bin/python -m pytest tests/test_embed_parity.py -q -s
```

ต้องผ่านทุกข้อ ค่า cosine ต้อง ≥ 0.99 และลำดับผลค้นคืนต้องตรงกับตอนใช้โมเดลในเครื่อง

ผลที่วัดไว้กับ Cloudflare เมื่อ 24 ส.ค. 2026 คือ **cosine 0.999999** ทุก query
และ calibration ผ่าน endpoint จริงยังได้ in-scope 14/14, off-topic 0/5, missing-law 0/5
เท่ากับตอนรันโมเดลในเครื่อง

### 2. push ขึ้น GitHub

commit แรกทำไว้แล้วในเครื่อง ยังไม่ได้ push ที่ไหน

```bash
cd ~/thai-law-bot
gh repo create thai-law-bot --private --source=. --remote=origin --push
```

หรือถ้าสร้าง repo เองผ่านเว็บ

```bash
git remote add origin https://github.com/<user>/thai-law-bot.git
git branch -M main && git push -u origin main
```

repo ราว 126 MB เพราะมี index ติดไปด้วย ทุกไฟล์ต่ำกว่าลิมิต 100 MB ต่อไฟล์ของ GitHub
`data/raw/` (383 MB) ไม่ถูก commit

### 3. สร้าง service บน Render

Dashboard → **New** → **Blueprint** → เลือก repo → Render อ่าน `render.yaml` เอง
ไม่ต้องกรอก build/start command

ตรวจว่าได้ค่าตามนี้

- Runtime **Docker**, Plan **Free**, Region **Singapore**
- Health check path `/health`

### 4. ใส่ secrets

Environment → Add Environment Variable (ใน `render.yaml` ตั้ง `sync: false` ไว้ จึงต้องกรอกตรงนี้)

| Key | ค่า |
|---|---|
| `EMBED_API_KEY` | Cloudflare API token |
| `EMBED_BASE_URL` | `https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1` |
| `TYPHOON_API_KEY` | คีย์ Typhoon |
| `LINE_CHANNEL_SECRET` | จาก LINE Console |
| `LINE_CHANNEL_ACCESS_TOKEN` | จาก LINE Console |
| `LINE_BOT_USER_ID` | จาก `GET /v2/bot/info` |

> คีย์ Typhoon และ LINE ชุดเดิมเคยถูกวางไว้ในแชท **ให้ออกใหม่ทั้งสองที่ก่อน** แล้วค่อยเอาชุดใหม่มาใส่

### 5. เช็กว่าขึ้นจริง

```bash
curl -s https://<service>.onrender.com/health
```

ต้องได้ `"chunks":27203`, `"dense_index":true`, `"llm_configured":true`, `"line_configured":true`

ลองค้นคืนโดยไม่เปลือง LLM

```bash
curl -sG https://<service>.onrender.com/search --data-urlencode "q=ถูกเลิกจ้าง ได้ค่าชดเชยเท่าไหร่"
```

### 6. ชี้ webhook ของ LINE มาที่นี่

LINE Developers Console → Messaging API → Webhook URL

```
https://<service>.onrender.com/webhook
```

กด **Verify** แล้วเปิด **Use webhook**

หรือสั่งจากเครื่องทีเดียวจบ (เช็ก `/health` ก่อน แล้วค่อยตั้งและให้ LINE ยิงทดสอบ)

```bash
scripts/point_line_at.sh https://<service>.onrender.com
```

สคริปต์จะไม่ยอมตั้งถ้า URL นั้นไม่ได้เสิร์ฟบอทตัวนี้ เพราะการตั้ง endpoint ผิดคืน 200 เหมือนกัน
อาการเดียวที่ได้คือบอทเงียบ

คราวนี้ URL นิ่งถาวร ไม่ต้องแก้ทุกครั้งเหมือนตอนใช้ cloudflared quick tunnel

**เสร็จแล้วปิดของในเครื่อง** ไม่งั้น tunnel ยังรันค้างและ LINE ก็ไม่ได้ชี้มาแล้ว

```bash
pkill -f 'cloudflared tunnel'
pkill -f 'uvicorn app.main:app'
```

### 7. กัน spin-down ด้วย UptimeRobot

Render free จะหลับหลังไม่มี traffic เข้ามา 15 นาที และตื่นใช้เวลาราว 1 นาที
ซึ่งนานกว่าอายุ reply token ของ LINE คำถามแรกหลังหลับจึงหาย

UptimeRobot → New Monitor

- Type **HTTP(s)**
- URL `https://<service>.onrender.com/health`
- Interval **5 นาที**

**ข้อควรระวังเรื่องโควตา** Render ให้ 750 free instance hours ต่อ workspace ต่อเดือน
เดือนหนึ่งยาวสุด 744 ชั่วโมง การ ping ให้ตื่นตลอดเวลาจึงพอดีโควตา
แต่พอสำหรับ **service ฟรีตัวเดียวเท่านั้น** ถ้ามีตัวที่สองในบัญชีเดียวกันจะเกินและถูกระงับ

---

## ค่าใช้จ่ายรวม

| รายการ | ต่อเดือน |
|---|---|
| Render free | $0 |
| Typhoon (beta ฟรี) | $0 |
| Cloudflare Workers AI | $0 (ฟรี 10,000 neurons/วัน ≈ 230,000 คำถาม/วัน) |
| UptimeRobot free | $0 |

ถ้าไม่อยากเสี่ยงเรื่องโควตา 750 ชั่วโมงหรือ 0.1 CPU ตัวเลือกถัดไปคือ Render Starter $7/เดือน
(ไม่หลับ แต่ยัง 512 MB ซึ่งพอแล้วเพราะ peak 227 MB)

---

## แก้ปัญหา

**deploy ล้มตอน build** — ดู log ว่าไฟล์ index ถูก push ขึ้นไปครบไหม
`.gitignore` ปล่อยผ่านไว้แค่ 4 ไฟล์ `corpus.jsonl`, `vectors.npy`, `bm25_compact.npz`, `bm25_vocab.json`

```bash
git ls-files data/ | cat
```

**`/health` ตอบ 200 แต่ถามแล้วเงียบ** — ดู log หา `warm-up query failed`
แปลว่า `EMBED_API_KEY` หรือ `EMBED_BASE_URL` ผิด หรือใช้ neurons เกินโควตาวันนั้น
service จะไม่ตายแต่ตอบไม่ได้ ดูโควตาที่ dash.cloudflare.com > AI > Workers AI

**บอทตอบช้ามากคำถามแรกของวัน** — service หลับไป ตรวจว่า UptimeRobot ยังเดินอยู่

**`index/corpus mismatch`** — `vectors.npy` กับ `corpus.jsonl` คนละรุ่นกัน
สร้างใหม่ในเครื่องด้วย `python -m ingest.build_index --dense` แล้ว push ใหม่

---

## รันในเครื่องแบบเดียวกับบน Render

```bash
docker build -t thai-law-bot .
docker run --rm -p 8000:8000 --memory 512m --cpus 0.1 \
  -e EMBED_API_KEY=... \
  -e EMBED_BASE_URL=https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1 \
  -e TYPHOON_API_KEY=... \
  -e LINE_CHANNEL_SECRET=... -e LINE_CHANNEL_ACCESS_TOKEN=... \
  thai-law-bot
```

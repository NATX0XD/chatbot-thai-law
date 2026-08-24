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
3. **DeepInfra API key** — https://deepinfra.com/dash/api_keys
   `BAAI/bge-m3` ราคา **$0.010 ต่อ 1M tokens** คำถามหนึ่งครั้งกินราว 40 tokens
   คิดเป็นราว **$0.0004 ต่อคำถาม 1,000 ครั้ง** ถือว่าเท่ากับฟรี
   ถ้าไม่อยากใช้ DeepInfra เปลี่ยนได้ที่ `EMBED_BASE_URL` + `EMBED_API_MODEL` โดยไม่ต้องแก้โค้ด
   ขอแค่เจ้านั้นเสิร์ฟ `BAAI/bge-m3` ตัวเดียวกัน (เช่น OVHcloud AI Endpoints)
   **SiliconFlow ใช้ไม่ได้** เพราะสมัครต้องใช้เบอร์โทรจีน

---

## ขั้นตอน

### 1. ตรวจว่า embedding จากผู้ให้บริการตรงกับ index

ข้อนี้สำคัญที่สุดและต้องทำ **ก่อน** deploy ถ้าเจ้านั้นเสิร์ฟคนละ checkpoint
cosine จะเลื่อนหมด เกณฑ์ `min_dense_sim = 0.54` จะไม่ได้แปลว่าอะไรอีกต่อไป
และอาการจะออกมาเป็น "ตอบแย่ลง" เงียบ ๆ ไม่ใช่ error

```bash
cd ~/thai-law-bot
EMBED_API_KEY=<คีย์ DeepInfra> .venv/bin/python -m pytest tests/test_embed_parity.py -q -s
```

ต้องผ่านทุกข้อ ค่า cosine ต้อง ≥ 0.99 (ปกติจะได้ 0.999x) และลำดับผลค้นคืนต้องตรงกับตอนใช้โมเดลในเครื่อง

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
| `EMBED_API_KEY` | คีย์ DeepInfra |
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
คราวนี้ URL นิ่งถาวร ไม่ต้องแก้ทุกครั้งเหมือนตอนใช้ cloudflared quick tunnel

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
| DeepInfra embeddings | ~$0.0004 ต่อคำถาม 1,000 ครั้ง |
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
แปลว่า `EMBED_API_KEY` ผิดหรือหมดเครดิต service จะไม่ตายแต่ตอบไม่ได้

**บอทตอบช้ามากคำถามแรกของวัน** — service หลับไป ตรวจว่า UptimeRobot ยังเดินอยู่

**`index/corpus mismatch`** — `vectors.npy` กับ `corpus.jsonl` คนละรุ่นกัน
สร้างใหม่ในเครื่องด้วย `python -m ingest.build_index --dense` แล้ว push ใหม่

---

## รันในเครื่องแบบเดียวกับบน Render

```bash
docker build -t thai-law-bot .
docker run --rm -p 8000:8000 --memory 512m --cpus 0.1 \
  -e EMBED_API_KEY=... -e TYPHOON_API_KEY=... \
  -e LINE_CHANNEL_SECRET=... -e LINE_CHANNEL_ACCESS_TOKEN=... \
  thai-law-bot
```

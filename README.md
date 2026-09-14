# Pocket Money Manager for Kenyan Teachers

**Free & Open Source** web dashboard that automatically matches incoming M-Pesa payments (to a personal number) to the correct student using the parent's phone number.

## Features

- **Students** with unique Student ID / Admission number
- **Parents / Guardians** – one student can have multiple parents; one parent can have multiple children
- **Automatic allocation**: when money arrives via M-Pesa SMS, the system looks up the sender’s phone → finds the parent → links to the student
- **Unallocated money is clearly highlighted** so the teacher can manually assign it
- Simple password-protected dashboard
- Works with any free Android SMS-to-webhook forwarder
- 100% free, runs on SQLite, no paid services required

## How the automation works

1. Teacher receives M-Pesa on their **personal number** (as usual).
2. An Android app on the same phone forwards the SMS to this web app’s webhook.
3. The web app parses the SMS (amount, transaction code, sender phone & name).
4. It matches the phone number against registered parents.
5. If exactly one student is linked → money is auto-allocated.
6. If zero or multiple students → it stays **Unallocated** and appears in red on the dashboard for manual allocation.

> **Note on phone masking**: Safaricom sometimes partially masks sender numbers (e.g. `0705***734`). The system tries a smart partial match; if it can’t be sure it leaves the payment unallocated.

## Quick Start (Local)

```bash
# 1. Install dependencies (Python 3.10+)
pip install flask flask-sqlalchemy

# 2. Run
cd pocket_money_kenya
python app.py
```

Open http://127.0.0.1:5000  
Default password: `teacher123`

Change the password by setting environment variable:
```bash
export APP_PASSWORD="your-strong-password"
export SECRET_KEY="a-long-random-string"
python app.py
```

## Deploy for free (so the phone can reach it)

Recommended free options:

| Platform     | Notes                                      | Free tier |
|--------------|--------------------------------------------|-----------|
| **Render**   | Easy, supports Python                      | Yes       |
| **Railway**  | Very simple                                | Yes (credit) |
| **Fly.io**   | Good performance                           | Yes       |
| **PythonAnywhere** | Beginner friendly                    | Yes       |

Example on Render:
1. Push this folder to a GitHub repo.
2. Create a new Web Service on Render, connect the repo.
3. Build command: `pip install flask flask-sqlalchemy`
4. Start command: `python app.py`
5. Add environment variables `APP_PASSWORD` and `SECRET_KEY`.
6. After deploy you get a public URL like `https://your-app.onrender.com`

Your webhook will be:  
`https://your-app.onrender.com/webhook/sms`

## Connect the phone (SMS Forwarder)

Install a free open-source Android SMS forwarder and point it at the webhook.

**Recommended apps:**

1. **SMS to URL Forwarder** (F-Droid)  
   https://f-droid.org/packages/tech.bogomolov.incomingsmsgateway/  
   - Set filter to sender `MPESA` or `*`  
   - URL = your webhook  
   - Method = POST  

2. **Upeo SMS Gateway** (built for M-Pesa use cases)  
   https://github.com/Upeosoft-Limited/upeo-sms-gateway

3. **sms2webhook**  
   https://github.com/rossigee/sms2webhook

After installing:
- Grant SMS permission
- Disable battery optimization for the app
- Keep the phone charged / plugged in if possible
- Test by sending a small amount from another number that you have already registered as a parent

## Recommended workflow for teachers

1. Add all **Students** (with their admission / student ID).
2. Add **Parents** and tick the children they are linked to.
3. Install the SMS forwarder on the phone that receives M-Pesa.
4. When money comes in it appears automatically.
5. Check the red **Unallocated** section every day and assign any that didn’t match (new numbers, masked numbers, or parents with multiple children).

## Data model

- `students` – student_id (unique), name, class, notes
- `parents` – name, phone (normalized to 2547…), notes
- `student_parents` – many-to-many link
- `transactions` – amount, mpesa_code, sender_phone, status (allocated / unallocated / manual), linked student

## Security notes

- Change the default password immediately.
- The webhook is currently open (anyone who knows the URL can post). For production you can add a secret token in the forwarder header and check it in `webhook_sms`.
- Keep the phone that receives M-Pesa SMS secure.

## License

MIT – free for every Kenyan teacher to use, modify and share.

---

Built for teachers who are tired of writing M-Pesa messages in exercise books.

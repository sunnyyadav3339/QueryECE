# Deploying QueryECE on Azure for Students

The result is the app at `https://<your-name>.<region>.cloudapp.azure.com`, with a
free HTTPS certificate, running all the time so the weekly crawl and email
alerts keep working. Allow 30–45 minutes the first time.

Everything runs with Docker on one small Linux server:

```
Internet ──► Caddy (HTTPS, ports 80/443) ──┬─ /api/*  ──► backend  (FastAPI, port 8000)
                                           └─ else    ──► frontend (Next.js, port 3000)
data/  (database, search index, photos, embedding model) is a folder on the server
```

## 1. Create the server (Azure portal)

1. Activate **Azure for Students** at <https://azure.microsoft.com/free/students>
   with your `@iitr.ac.in` email (no card needed; $100 credit).
2. In the portal: **Create a resource → Virtual machine**.
   - Resource group: new, e.g. `queryece`
   - Name: `queryece`
   - Region: **Central India** (closest; any region works)
   - Image: **Ubuntu Server 24.04 LTS**
   - Size: **B2s** (2 vCPU, 4 GB RAM). The embedding model needs about 1 GB; 1 GB machines are too small.
   - Authentication: **SSH public key**, username `azureuser`; download the `.pem` key when asked.
   - Inbound ports: allow **SSH (22), HTTP (80), HTTPS (443)**.
3. After it's created, open the VM → **Overview → DNS name → Configure**, and set a
   DNS name label, e.g. `queryece`. Your address becomes
   `queryece.centralindia.cloudapp.azure.com`. Note it down.

Credit check: a B2s VM costs roughly $30–40/month, so the $100 credit lasts about
3 months. Stop the VM in the portal when you don't need it (a stopped VM costs
almost nothing), and check **Cost Management** occasionally.

## 2. Install Docker on the server

From Git Bash on your laptop (use the path of the key you downloaded):

```bash
chmod 400 ~/Downloads/queryece_key.pem
ssh -i ~/Downloads/queryece_key.pem azureuser@queryece.centralindia.cloudapp.azure.com
```

Then, on the server:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker azureuser
exit
```

Log in again (the `ssh` command above) so the Docker permission applies.

## 3. Get the code

On the server:

```bash
git clone https://github.com/sunnyyadav3339/QueryECE.git
cd QueryECE
```

(If the repository is private, GitHub asks you to sign in; use a personal access
token as the password.)

## 4. Copy your settings and data

Do this **from your laptop** (in Git Bash, inside your local `QueryECE` folder), so
the server gets your existing accounts, chats, insights, photos and search index.
Stop the app on your laptop first.

```bash
scp -i ~/Downloads/queryece_key.pem backend/.env azureuser@queryece.centralindia.cloudapp.azure.com:QueryECE/backend/.env
tar czf data.tgz data
scp -i ~/Downloads/queryece_key.pem data.tgz azureuser@queryece.centralindia.cloudapp.azure.com:QueryECE/
```

Then on the server:

```bash
cd ~/QueryECE && tar xzf data.tgz && rm data.tgz
```

## 5. Point the app at its address

On the server, edit `backend/.env` (`nano backend/.env`) and set:

```
APP_URL=https://queryece.centralindia.cloudapp.azure.com
CORS_ORIGINS=https://queryece.centralindia.cloudapp.azure.com
ENABLE_SCHEDULER=true
```

Keep the Groq key and the `SMTP_*` lines as they are. Then create the file that
tells Caddy the address:

```bash
echo "DOMAIN=queryece.centralindia.cloudapp.azure.com" > .env
```

## 6. Start it

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The first build takes 5–10 minutes. Then open
`https://queryece.centralindia.cloudapp.azure.com`. Caddy gets the HTTPS
certificate on the first visit (a few seconds).

Useful commands on the server:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml restart
```

## Updating to a newer version

After pushing changes to GitHub from your laptop:

```bash
cd ~/QueryECE && git pull && docker compose -f docker-compose.prod.yml up -d --build
```

## Backups

All users, chats, insights and outreach live in `data/queryece.db`. Copy it to your
laptop now and then:

```bash
scp -i ~/Downloads/queryece_key.pem azureuser@queryece.centralindia.cloudapp.azure.com:QueryECE/data/queryece.db ./queryece-backup.db
```

## Notes

- **Faculty photos** are fetched from channeli.in, which only works on the IIT Roorkee
  network. The server keeps the photos you copied in step 4; to refresh them, run
  `python -m app.ingest.photos` on your laptop while on campus Wi-Fi or VPN and copy
  `data/photos/` up again.
- **Email** works from Azure over port 587 (Gmail). Azure only blocks port 25.
- **One backend worker** is intentional: the weekly crawl and email jobs run inside it
  and must run once.
- If the site doesn't load, check that ports 80 and 443 are open in the VM's
  **Networking** settings and that `DOMAIN` matches the DNS name exactly.

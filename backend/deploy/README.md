# Despliegue minimo en AWS EC2 con Miniconda

Este backend usa `FastAPI` y `uvicorn`. Para este proyecto, el flujo recomendado es:

1. Mantener el entorno en `Miniconda`
2. Ejecutar la API con `systemd`
3. Publicarla con `Nginx`

## 1. Requisitos

La guia asume que ya tienes:

- una instancia EC2 activa
- el repositorio clonado en `/home/ubuntu/invoice/invoice_octagon`
- tu archivo `.env` en `/home/ubuntu/invoice/invoice_octagon/backend/.env`
- tu entorno conda funcionando

Si `nginx` no esta instalado:

```bash
sudo apt update
sudo apt install -y nginx
```

## 2. Servicio systemd

Este repo incluye el archivo [invoice-api.service](F:\Octagon\repositories\invoice_octagon\backend\deploy\invoice-api.service) apuntando al entorno:

```bash
/home/ubuntu/miniconda3/envs/octagon/bin/uvicorn
```

Copialo al sistema y activalo:

```bash
cd /home/ubuntu/invoice/invoice_octagon/backend
sudo cp deploy/invoice-api.service /etc/systemd/system/invoice-api.service
sudo systemctl daemon-reload
sudo systemctl enable invoice-api
sudo systemctl start invoice-api
sudo systemctl status invoice-api
```

## 3. Nginx

> `invoice-api.nginx.conf` ahora usa `server_name api.octagonpr.co` (ya no `_`).
> El DNS de ese dominio debe apuntar a la EC2 **antes** de recargar nginx.

```bash
cd /home/ubuntu/invoice/invoice_octagon/backend
sudo cp deploy/invoice-api.nginx.conf /etc/nginx/sites-available/invoice-api
sudo ln -s /etc/nginx/sites-available/invoice-api /etc/nginx/sites-enabled/invoice-api
sudo nginx -t
sudo systemctl restart nginx
```

## 3.1 HTTPS con certbot (REQUERIDO para el bot de Telegram)

Telegram exige HTTPS válido para el webhook. Con el bloque HTTP:80 ya activo y el
DNS apuntando a la EC2:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.octagonpr.co
sudo nginx -t && sudo systemctl reload nginx
```

`certbot --nginx` obtiene el certificado y **reescribe** el archivo agregando el
bloque `listen 443 ssl` + la redirección 80→443 (ver el bloque de referencia
comentado en `invoice-api.nginx.conf`). Verifica:

```bash
curl -I https://api.octagonpr.co/health   # debe responder 200 por HTTPS
```

La renovación es automática (timer de certbot); pruébala con
`sudo certbot renew --dry-run`.

## 4. Verificacion

Probar dentro de la instancia:

```bash
curl http://127.0.0.1:8000/health
```

Probar desde fuera:

```bash
curl http://TU_IP_PUBLICA/health
```

## 5. Logs utiles

```bash
sudo journalctl -u invoice-api -f
sudo systemctl restart invoice-api
```

## 6. Bot de Telegram (webhook) — Fase 2

Requisitos previos: HTTPS ya funcionando (sección 3.1) y estas claves en
`backend/.env`:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_SECRET=...   # string aleatorio, ej. `openssl rand -hex 16`
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-sonnet-4-5
```

Pasos:

1. Aplicar el SQL nuevo en el editor de Supabase: `backend/supabase_script/telegram_bot.sql`.
2. Traer el código y reinstalar dependencias (agrega `httpx`), luego reiniciar:

   ```bash
   cd /home/ubuntu/invoice/invoice_octagon
   git checkout fase2-telegram && git pull
   /home/ubuntu/miniconda3/envs/octagon/bin/pip install -r backend/requirements.txt
   sudo systemctl restart invoice-api
   ```

3. Registrar el webhook (webhook y long polling son excluyentes: al registrarlo,
   NO corras `bot_polling`):

   ```bash
   cd /home/ubuntu/invoice/invoice_octagon/backend
   /home/ubuntu/miniconda3/envs/octagon/bin/python scripts/set_webhook.py set https://api.octagonpr.co/telegram/webhook
   ```

4. Verificar que quedó bien (sin `last_error_message`):

   ```bash
   /home/ubuntu/miniconda3/envs/octagon/bin/python scripts/set_webhook.py info
   ```

5. Probar desde el teléfono; manda dos mensajes seguidos rápido y confirma que no
   se duplica el invoice.

Para volver a long polling (dev): `python scripts/set_webhook.py delete`.

> Nota: el servicio corre con `--workers 2`. El flujo `/register` (email→password)
> guarda estado en memoria por proceso, así que puede fallar entre workers. Para
> registrar usuarios de forma fiable, hazlo con `--workers 1` temporalmente o vía
> long polling local.

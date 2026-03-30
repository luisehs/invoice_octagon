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

```bash
cd /home/ubuntu/invoice/invoice_octagon/backend
sudo cp deploy/invoice-api.nginx.conf /etc/nginx/sites-available/invoice-api
sudo ln -s /etc/nginx/sites-available/invoice-api /etc/nginx/sites-enabled/invoice-api
sudo nginx -t
sudo systemctl restart nginx
```

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

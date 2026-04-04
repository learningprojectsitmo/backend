There are three docker containers:
1. Backend
1. Frontend
1. Database (postgres)
Get current db schema:

```bash
docker exec -it <container_id> bash -c "export PGPASSWORD=password && pg_dump -h postgres -U postgres -s -d backend_db" > schema.sql
```

import psycopg

def query(sql: str):
    return psycopg.connect("postgresql://localhost/app")

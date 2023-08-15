from fastapi import FastAPI
import psycopg2
from psycopg2 import pool
import pandas as pd

app = FastAPI()

# PostgreSQL connection parameters
db_params = {
    "database": "futures",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": "5432",
    "minconn": 1,
    "maxconn": 3,
}


CONN_POOL = psycopg2.pool.SimpleConnectionPool(**db_params)

lookup = pd.read_csv('/Users/you-know-who/Code/Project/stock_server/smartapi/.lookup/2023_week_32.csv')
lookup.dropna(how='any', inplace=True)
lookup.set_index('token', inplace=True)

@app.on_event("shutdown")
def shutdown():
    CONN_POOL.closeall()


@app.get("/movements")
async def get_movements():
    interval = 3
    growth_threshold = .2

    try:
        conn = CONN_POOL.getconn()
        df = pd.read_sql(f"select * from token_movements(interval '{interval} minutes')", conn, columns=['token', 'accel', 'price'])
        CONN_POOL.putconn(conn)

        df['isUp'] = df['accel'].abs() >= growth_threshold

        res = []
        for id, row in df.iterrows():
            token = row['token']
            if token not in lookup.index: continue

            symbol = lookup.loc[token]['symbol']
            accel = row['accel']
            price = row['price']
            if isUp >= 0.2:
                isUp = 1
            elif isUp <= -0.2:
                isUp = -1
            else:
                isUp = 0

            res.append({
                'token': token,
                'symbol': symbol,
                'change': accel,
                'ltp': price,
                'isUp': isUp
            })

        return { "data": res }

    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

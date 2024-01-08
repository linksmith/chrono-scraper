from typing import Union
from fastapi import FastAPI
# from .worker import some_task

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/search")
def search(query: str):
    # Conduct search with filters
    search_params = {
        # 'filter': f'timestamp >= {min_date_timestamp} AND timestamp < {max_date_timestamp}',
        'attributesToHighlight': ['text'],
        'attributesToCrop': ['text'],
        'cropLength': 36,
        'highlightPreTag': "**",
        'highlightPostTag': "**",
        'limit': 10,
        # 'offset': st.session_state.offset,
        # 'showRankingScore': True
    }
    
    results = search(query, search_params)
    
    return results

@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}


# @app.post('/some_endpoint/')
# async def trigger_task():
#     arg1, arg2 = None
#     some_task.delay(arg1, arg2)
#     return {"status": "Task started"}


import os
from pathlib import Path
from typing import Dict, Any
from sqlalchemy import text

class QueryLoader:
    def __init__(self, queries_dir: str = "app/db/queries"):
        self.queries_dir = Path(queries_dir)
        self.queries: Dict[str, str] = {}
        self.load_queries()
    
    def load_queries(self):
        """모든 .sql 파일 로드"""
        for sql_file in self.queries_dir.glob("*.sql"):
            query_name = sql_file.stem  # 파일명 (확장자 제외)
            with open(sql_file, 'r', encoding='utf-8') as f:
                self.queries[query_name] = f.read()
    
    def get_query(self, name: str, **params) -> text:
        """쿼리 반환 (파라미터 치환 가능)"""
        query = self.queries.get(name)
        if not query:
            raise ValueError(f"쿼리 '{name}'를 찾을 수 없습니다.")
        return text(query)
    
    def list_queries(self):
        return list(self.queries.keys())

# 싱글톤 인스턴스
query_loader = QueryLoader()
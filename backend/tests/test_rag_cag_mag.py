from app.rag.agentic import RetrievalRequest
from app.rag.embeddings import LocalEmbedder, tokenize


def test_football_vocabulary_normalised():
    assert "press" in tokenize("pressing pressure")
    assert "flank" in tokenize("down the wing")


def test_embeddings_semantic_neighbourhood():
    e = LocalEmbedder()
    a, b, c = (e.embed_one(t) for t in ("right-back overlapping on the right flank", "full-back overlap flank cross",
                                         "goalkeeper distribution short passes"))
    dot = lambda x, y: sum(i * j for i, j in zip(x, y))  # noqa: E731
    assert dot(a, b) > dot(a, c)


async def test_retrieval_not_needed_when_cag_sufficient(container):
    plan = container.retriever.plan(RetrievalRequest(reason="question", intent="STATS", cached_context_sufficient=True))
    assert not plan.needed


async def test_agentic_retrieval_finds_relevant_history(container):
    res = await container.retriever.retrieve(RetrievalRequest(reason="pattern_start", teams=["tha", "azc"],
                                                              players=["tha_2"], patterns=["FLANK_OVERLOAD"]))
    titles = [d["title"] for d in res.documents]
    assert any("Matchday 7" in t or "Matchday 3" in t for t in titles)
    assert res.documents[0]["rerank_score"] >= res.documents[-1]["rerank_score"]
    assert all(d["why_selected"] is not None for d in res.documents)
    assert res.trace and res.trace[0].startswith("plan:")


async def test_retrieval_replans_when_evidence_weak(container):
    res = await container.retriever.retrieve(RetrievalRequest(reason="pattern_start", teams=["nobody"],
                                                              patterns=["MIDFIELD_SUPERIORITY"]))
    assert res.rounds == 2 and any("re-plan" in t for t in res.trace)


async def test_cag_versioning(loaded):
    c, rt = loaded
    v1 = (await c.cag.get(rt.match_id))["version"]
    ctx = await c.cag.refresh(rt)
    assert ctx["version"] == v1 + 1
    assert ctx["score"] == rt.engine.score and len(ctx["last_events"]) == 20


async def test_mag_personal_memories_are_private(container):
    alex = await container.memory.recall("pressing Harbour United", entities=["azc"], user_id="alex", k=6)
    sam = await container.memory.recall("pressing Harbour United", entities=["azc"], user_id="sam", k=6)
    assert any(m["kind"] == "conversation" for m in alex)
    assert not any(m["memory_id"] == "mem_user_alex_press" for m in sam)


async def test_mag_entity_recall(container):
    mems = await container.memory.recall("right flank overlaps", entities=["tha", "tha_2"], k=3)
    assert mems and mems[0]["memory_id"] == "mem_tha_rightflank"

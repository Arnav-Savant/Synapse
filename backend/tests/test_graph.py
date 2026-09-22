from app.knowledge.frontmatter import ParsedConcept, Relationship
from app.knowledge.graph import build_graph


def concept(id_, title=None, relationships=None, body="", domains=None, aliases=None, status="stub"):
    return ParsedConcept(
        id=id_,
        title=title or id_,
        aliases=aliases or [],
        domains=domains or [],
        status=status,
        relationships=relationships or [],
        body=body,
    )


def test_multi_parent_subtopic_of():
    concepts = [
        concept("prompt-injection", relationships=[
            Relationship(type="subtopic-of", target="prompt-engineering"),
            Relationship(type="subtopic-of", target="llm-security"),
        ]),
        concept("prompt-engineering"),
        concept("llm-security"),
    ]

    graph = build_graph(concepts)

    edges = {(e.source, e.target, e.type) for e in graph.edges}
    assert ("prompt-injection", "prompt-engineering", "subtopic-of") in edges
    assert ("prompt-injection", "llm-security", "subtopic-of") in edges
    assert graph.warnings == []
    subtopic_edge = next(e for e in graph.edges if e.target == "prompt-engineering")
    assert subtopic_edge.inverse_type == "has-subtopic"
    assert subtopic_edge.implicit is False


def test_contrasts_with_symmetric_edge_stored_once():
    concepts = [
        concept("few-shot-prompting", relationships=[
            Relationship(type="contrasts-with", target="zero-shot-prompting"),
        ]),
        concept("zero-shot-prompting"),
    ]

    graph = build_graph(concepts)

    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.type == "contrasts-with"
    assert edge.inverse_type == "contrasts-with"


def test_symmetric_relationship_declared_on_both_sides_stored_once():
    # CLAUDE.md tells the processing engine to declare a symmetric
    # relationship on only one side, but a real run has been observed to
    # declare it on both — this must not produce two edges.
    concepts = [
        concept("chain-of-thought-prompting", relationships=[
            Relationship(type="related-to", target="few-shot-prompting"),
        ]),
        concept("few-shot-prompting", relationships=[
            Relationship(type="related-to", target="chain-of-thought-prompting"),
        ]),
    ]

    graph = build_graph(concepts)

    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.type == "related-to"
    assert {edge.source, edge.target} == {"chain-of-thought-prompting", "few-shot-prompting"}


def test_wikilink_only_implicit_edge():
    concepts = [
        concept("prompt-engineering", body="See [[few-shot-prompting]] for an example."),
        concept("few-shot-prompting"),
    ]

    graph = build_graph(concepts)

    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.source == "prompt-engineering"
    assert edge.target == "few-shot-prompting"
    assert edge.type == "related-to"
    assert edge.implicit is True


def test_wikilink_suppressed_when_frontmatter_already_connects_pair():
    concepts = [
        concept(
            "prompt-injection",
            relationships=[Relationship(type="subtopic-of", target="prompt-engineering")],
            body="See [[prompt-engineering]] for context.",
        ),
        concept("prompt-engineering"),
    ]

    graph = build_graph(concepts)

    assert len(graph.edges) == 1
    assert graph.edges[0].type == "subtopic-of"
    assert graph.edges[0].implicit is False


def test_broken_relationship_target_produces_warning_not_crash():
    concepts = [
        concept("prompt-injection", relationships=[
            Relationship(type="subtopic-of", target="does-not-exist"),
        ]),
    ]

    graph = build_graph(concepts)

    assert graph.edges == []
    assert len(graph.warnings) == 1
    assert "does-not-exist" in graph.warnings[0]


def test_broken_wikilink_target_produces_warning_not_crash():
    concepts = [
        concept("prompt-engineering", body="See [[nonexistent-concept]]."),
    ]

    graph = build_graph(concepts)

    assert graph.edges == []
    assert len(graph.warnings) == 1
    assert "nonexistent-concept" in graph.warnings[0]


def test_self_referencing_wikilink_ignored():
    concepts = [
        concept("prompt-engineering", body="See [[prompt-engineering]] itself."),
    ]

    graph = build_graph(concepts)

    assert graph.edges == []
    assert graph.warnings == []


def test_nodes_include_aliases_domains_status():
    concepts = [
        concept("few-shot-prompting", aliases=["Few-shot learning"], domains=["prompt-engineering"], status="developing"),
    ]

    graph = build_graph(concepts)

    assert len(graph.nodes) == 1
    node = graph.nodes[0]
    assert node.aliases == ["Few-shot learning"]
    assert node.domains == ["prompt-engineering"]
    assert node.status == "developing"

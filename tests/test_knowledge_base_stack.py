from __future__ import annotations

import json

from aws_cdk import App
from aws_cdk.assertions import Match, Template

from stacks.knowledge_base_stack import HermesKnowledgeBaseStack


def _template() -> Template:
    app = App(context={"project_name": "hermes-test"})
    return Template.from_stack(HermesKnowledgeBaseStack(app, "KnowledgeBase"))


def test_knowledge_base_uses_private_encrypted_document_bucket_and_s3_vectors():
    template = _template()
    template.has_resource_properties("AWS::S3::Bucket", Match.object_like({
        "BucketEncryption": Match.any_value(),
        "PublicAccessBlockConfiguration": Match.object_like({"BlockPublicAcls": True}),
    }))
    template.resource_count_is("AWS::S3Vectors::VectorBucket", 1)
    template.has_resource_properties("AWS::S3Vectors::Index", Match.object_like({
        "Dimension": 1024,
        "DataType": "float32",
        "DistanceMetric": "cosine",
    }))


def test_knowledge_base_uses_titan_v2_fixed_chunking_and_semantic_search():
    template = _template()
    resources = template.to_json()["Resources"]
    knowledge_base = next(value for value in resources.values() if value["Type"] == "AWS::Bedrock::KnowledgeBase")
    data_source = next(value for value in resources.values() if value["Type"] == "AWS::Bedrock::DataSource")

    assert "amazon.titan-embed-text-v2:0" in json.dumps(knowledge_base)
    assert data_source["Properties"]["DataSourceConfiguration"]["S3Configuration"]["InclusionPrefixes"] == ["knowledge-base/"]
    assert data_source["Properties"]["VectorIngestionConfiguration"] == {
        "ChunkingConfiguration": {"ChunkingStrategy": "FIXED_SIZE", "FixedSizeChunkingConfiguration": {"MaxTokens": 300, "OverlapPercentage": 20}},
    }


def test_knowledge_base_role_is_scoped_to_its_documents_embeddings_and_vector_index():
    template = _template()
    policies = json.dumps(template.find_resources("AWS::IAM::Policy"))
    assert "bedrock:InvokeModel" in policies
    assert "s3vectors:PutVectors" in policies
    assert "s3vectors:GetVectors" in policies
    assert "foundation-model/amazon.titan-embed-text-v2:0" in policies

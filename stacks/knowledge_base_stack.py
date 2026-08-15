"""Private product-document Knowledge Base backed by Amazon S3 Vectors."""

from __future__ import annotations

from pathlib import Path

from aws_cdk import CfnDeletionPolicy, CfnOutput, CfnResource, Fn, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3_deployment
from constructs import Construct


class HermesKnowledgeBaseStack(Stack):
    """Knowledge Base and immutable first S3 data source configuration."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        project = self.node.try_get_context("project_name") or "hermes-agentcore"
        account = Stack.of(self).account
        region = Stack.of(self).region

        self.document_bucket = s3.Bucket(
            self,
            "DocumentsBucket",
            bucket_name=f"{project}-knowledge-documents-{account}-{region}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )
        s3_deployment.BucketDeployment(
            self,
            "LumenSeedDocument",
            destination_bucket=self.document_bucket,
            destination_key_prefix="knowledge-base",
            sources=[s3_deployment.Source.asset(str(Path(__file__).parents[1] / "knowledge-base"))],
            prune=False,
        )

        self.vector_bucket = CfnResource(
            self,
            "VectorBucket",
            type="AWS::S3Vectors::VectorBucket",
            properties={"VectorBucketName": f"{project}-knowledge-vectors-{account}-{region}".lower()},
        )
        self.vector_bucket.cfn_options.deletion_policy = CfnDeletionPolicy.RETAIN
        self.vector_bucket.cfn_options.update_replace_policy = CfnDeletionPolicy.RETAIN
        self.vector_index = CfnResource(
            self,
            "VectorIndex",
            type="AWS::S3Vectors::Index",
            properties={
                "VectorBucketArn": self.vector_bucket.ref,
                "IndexName": "hermes-product-support",
                "DataType": "float32",
                "Dimension": 1024,
                "DistanceMetric": "cosine",
            },
        )
        self.vector_index.add_dependency(self.vector_bucket)
        self.vector_index.cfn_options.deletion_policy = CfnDeletionPolicy.RETAIN
        self.vector_index.cfn_options.update_replace_policy = CfnDeletionPolicy.RETAIN

        self.knowledge_base_role = iam.Role(
            self,
            "KnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": account},
                    "ArnLike": {"aws:SourceArn": Fn.sub("arn:${AWS::Partition}:bedrock:${AWS::Region}:${AWS::AccountId}:knowledge-base/*")},
                },
            ),
        )
        self.document_bucket.grant_read(self.knowledge_base_role)
        embedding_model_arn = Stack.of(self).format_arn(
            service="bedrock", region=region, account="", resource="foundation-model/amazon.titan-embed-text-v2:0"
        )
        self.knowledge_base_role.add_to_policy(iam.PolicyStatement(
            sid="InvokeTitanEmbeddingModel",
            actions=["bedrock:InvokeModel"],
            resources=[embedding_model_arn],
        ))
        self.knowledge_base_role.add_to_policy(iam.PolicyStatement(
            sid="AccessOnlyThisS3VectorIndex",
            actions=[
                "s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors",
                "s3vectors:QueryVectors", "s3vectors:GetIndex",
            ],
            resources=[self.vector_index.ref],
        ))

        self.knowledge_base = CfnResource(
            self,
            "KnowledgeBase",
            type="AWS::Bedrock::KnowledgeBase",
            properties={
                "Name": f"{project}-product-support",
                "Description": "Private product-support evidence for Hermes.",
                "RoleArn": self.knowledge_base_role.role_arn,
                "KnowledgeBaseConfiguration": {
                    "Type": "VECTOR",
                    "VectorKnowledgeBaseConfiguration": {
                        "EmbeddingModelArn": embedding_model_arn,
                        "EmbeddingModelConfiguration": {"BedrockEmbeddingModelConfiguration": {"Dimensions": 1024}},
                    },
                },
                "StorageConfiguration": {
                    "Type": "S3_VECTORS",
                    "S3VectorsConfiguration": {
                        "VectorBucketArn": self.vector_bucket.ref,
                        "IndexArn": self.vector_index.ref,
                        "IndexName": "hermes-product-support",
                    },
                },
            },
        )
        self.knowledge_base.add_dependency(self.vector_index)
        self.data_source = CfnResource(
            self,
            "ProductDocumentsDataSource",
            type="AWS::Bedrock::DataSource",
            properties={
                "Name": "product-documents",
                "Description": "Versioned product documents in the private Hermes bucket.",
                "KnowledgeBaseId": self.knowledge_base.ref,
                "DataDeletionPolicy": "RETAIN",
                "DataSourceConfiguration": {
                    "Type": "S3",
                    "S3Configuration": {
                        "BucketArn": self.document_bucket.bucket_arn,
                        "InclusionPrefixes": ["knowledge-base/"],
                    },
                },
                "VectorIngestionConfiguration": {
                    "ChunkingConfiguration": {
                        "ChunkingStrategy": "FIXED_SIZE",
                        "FixedSizeChunkingConfiguration": {"MaxTokens": 300, "OverlapPercentage": 20},
                    },
                },
            },
        )
        self.data_source.add_dependency(self.knowledge_base)

        CfnOutput(self, "KnowledgeBaseId", value=self.knowledge_base.ref)
        CfnOutput(self, "KnowledgeBaseArn", value=Fn.get_att(self.knowledge_base.logical_id, "KnowledgeBaseArn").to_string())
        CfnOutput(self, "DataSourceId", value=Fn.get_att(self.data_source.logical_id, "DataSourceId").to_string())
        CfnOutput(self, "DocumentsBucketName", value=self.document_bucket.bucket_name)

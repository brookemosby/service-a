from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
)
class BaselineStack(Stack):
    """Shared platform: network, cluster, load balancer, ECR, GitHub OIDC role."""

    def __init__(
        self,
        scope,
        construct_id,
        *,
        github_org,
        github_repo_a,
        github_repo_b,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Database",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        self.cluster = ecs.Cluster(self, "Cluster", vpc=self.vpc)

        self.ecr_service_a = ecr.Repository(
            self,
            "EcrServiceA",
            repository_name="service-a",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
        )
        self.ecr_service_b = ecr.Repository(
            self,
            "EcrServiceB",
            repository_name="service-b",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
        )

        self.alb = elbv2.ApplicationLoadBalancer(
            self,
            "Alb",
            vpc=self.vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        self.listener = self.alb.add_listener(
            "HttpListener",
            port=80,
            open=True,
            default_action=elbv2.ListenerAction.fixed_response(
                404,
                content_type="text/plain",
                message_body="No preview route matched",
            ),
        )

        oidc_provider = iam.OpenIdConnectProvider(
            self,
            "GitHubOidc",
            url="https://token.actions.githubusercontent.com",
            client_ids=["sts.amazonaws.com"],
            thumbprints=[
                "6938fd04d4836e0b163a24601d5cc7360e5e5bc0",
                "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
            ],
        )

        deploy_role = iam.Role(
            self,
            "GitHubDeployRole",
            assumed_by=iam.FederatedPrincipal(
                oidc_provider.open_id_connect_provider_arn,
                {
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                    },
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": [
                            f"repo:{github_org}@*/{github_repo_a}@*:*",
                            f"repo:{github_org}@*/{github_repo_b}@*:*",
                        ],
                    },
                },
                "sts:AssumeRoleWithWebIdentity",
            ),
            description="GitHub Actions deploy role for preview environments",
        )

        deploy_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
        )

        CfnOutput(self, "VpcId", value=self.vpc.vpc_id, export_name="PreviewVpcId")
        CfnOutput(
            self,
            "ClusterName",
            value=self.cluster.cluster_name,
            export_name="PreviewClusterName",
        )
        CfnOutput(
            self,
            "ListenerArn",
            value=self.listener.listener_arn,
            export_name="PreviewListenerArn",
        )
        CfnOutput(
            self,
            "AlbDnsName",
            value=self.alb.load_balancer_dns_name,
            export_name="PreviewAlbDnsName",
        )
        CfnOutput(
            self,
            "AlbSecurityGroupId",
            value=self.alb.connections.security_groups[0].security_group_id,
            export_name="PreviewAlbSecurityGroupId",
        )
        CfnOutput(
            self,
            "PublicSubnetIds",
            value=",".join(subnet.subnet_id for subnet in self.vpc.public_subnets),
            export_name="PreviewPublicSubnetIds",
        )
        CfnOutput(
            self,
            "DatabaseSubnetIds",
            value=",".join(
                subnet.subnet_id for subnet in self.vpc.isolated_subnets
            ),
            export_name="PreviewDatabaseSubnetIds",
        )
        CfnOutput(
            self,
            "EcrServiceAUri",
            value=self.ecr_service_a.repository_uri,
            export_name="PreviewEcrServiceAUri",
        )
        CfnOutput(
            self,
            "EcrServiceBUri",
            value=self.ecr_service_b.repository_uri,
            export_name="PreviewEcrServiceBUri",
        )
        CfnOutput(
            self,
            "GitHubDeployRoleArn",
            value=deploy_role.role_arn,
            export_name="PreviewGitHubDeployRoleArn",
        )

import json

from aws_cdk import (
    CfnOutput,
    Duration,
    Fn,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_rds as rds,
    aws_secretsmanager as secretsmanager,
)
class PreviewStack(Stack):
    def __init__(
        self,
        scope,
        construct_id,
        *,
        env_id,
        service_a_image,
        service_b_image,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        vpc_id = Fn.import_value("PreviewVpcId")
        cluster_name = Fn.import_value("PreviewClusterName")
        listener_arn = Fn.import_value("PreviewListenerArn")
        alb_sg_id = Fn.import_value("PreviewAlbSecurityGroupId")
        public_subnet_ids = Fn.split(",", Fn.import_value("PreviewPublicSubnetIds"))
        database_subnet_ids = Fn.split(",", Fn.import_value("PreviewDatabaseSubnetIds"))

        vpc = ec2.Vpc.from_vpc_attributes(
            self,
            "Vpc",
            vpc_id=vpc_id,
            availability_zones=Fn.get_azs(),
            public_subnet_ids=public_subnet_ids,
            isolated_subnet_ids=database_subnet_ids,
        )
        cluster = ecs.Cluster.from_cluster_attributes(
            self, "Cluster", cluster_name=cluster_name, vpc=vpc
        )
        alb_security_group = ec2.SecurityGroup.from_security_group_id(
            self, "AlbSecurityGroup", alb_sg_id
        )
        db_security_group = ec2.SecurityGroup(
            self, "DatabaseSecurityGroup", vpc=vpc, allow_all_outbound=False
        )
        service_security_group = ec2.SecurityGroup(
            self, "ServiceSecurityGroup", vpc=vpc, allow_all_outbound=True
        )
        db_security_group.add_ingress_rule(
            service_security_group, ec2.Port.tcp(5432)
        )

        db_credentials = secretsmanager.Secret(
            self,
            "DatabaseCredentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({"username": "preview"}),
                generate_string_key="password",
                exclude_punctuation=True,
                password_length=32,
            ),
        )
        database = rds.DatabaseInstance(
            self,
            "Database",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[db_security_group],
            credentials=rds.Credentials.from_secret(db_credentials),
            database_name="preview",
            allocated_storage=20,
            backup_retention=Duration.days(0),
            delete_automated_backups=True,
            removal_policy=RemovalPolicy.DESTROY,
            deletion_protection=False,
        )

        task_execution_role = iam.Role(
            self,
            "TaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )
        db_credentials.grant_read(task_execution_role)

        path_prefix = f"/preview/{env_id}"

        def add_service(
            *,
            service_id,
            image,
            service_name,
            api_suffix,
        ):
            task_definition = ecs.FargateTaskDefinition(
                self,
                f"{service_id}TaskDefinition",
                cpu=256,
                memory_limit_mib=512,
                execution_role=task_execution_role,
            )
            api_prefix = f"{path_prefix}/{api_suffix}"
            container = task_definition.add_container(
                service_id,
                image=ecs.ContainerImage.from_registry(image),
                logging=ecs.LogDrivers.aws_logs(stream_prefix=service_name),
                environment={
                    "DB_HOST": database.db_instance_endpoint_address,
                    "DB_PORT": database.db_instance_endpoint_port,
                    "DB_NAME": "preview",
                    "SERVICE_NAME": service_name,
                    "API_PREFIX": api_prefix,
                },
                secrets={
                    "DB_USER": ecs.Secret.from_secrets_manager(
                        db_credentials, field="username"
                    ),
                    "DB_PASSWORD": ecs.Secret.from_secrets_manager(
                        db_credentials, field="password"
                    ),
                },
            )
            container.add_port_mappings(
                ecs.PortMapping(container_port=8000, protocol=ecs.Protocol.TCP)
            )
            service = ecs.FargateService(
                self,
                service_id,
                cluster=cluster,
                task_definition=task_definition,
                desired_count=1,
                assign_public_ip=True,
                security_groups=[service_security_group],
                vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
                health_check_grace_period=Duration.seconds(180),
            )
            target_group = elbv2.ApplicationTargetGroup(
                self,
                f"{service_id}TargetGroup",
                vpc=vpc,
                port=8000,
                protocol=elbv2.ApplicationProtocol.HTTP,
                target_type=elbv2.TargetType.IP,
                health_check=elbv2.HealthCheck(
                    path=f"{api_prefix}/health",
                    healthy_http_codes="200",
                ),
            )
            service.attach_to_application_target_group(target_group)
            return service, target_group

        _, target_group_a = add_service(
            service_id="ServiceA",
            image=service_a_image,
            service_name="service-a",
            api_suffix="a",
        )
        _, target_group_b = add_service(
            service_id="ServiceB",
            image=service_b_image,
            service_name="service-b",
            api_suffix="b",
        )

        listener = elbv2.ApplicationListener.from_application_listener_attributes(
            self,
            "SharedListener",
            listener_arn=listener_arn,
            security_group=alb_security_group,
        )
        priority_base = abs(hash(env_id)) % 40000 + 1000
        elbv2.ApplicationListenerRule(
            self,
            "ServiceARoute",
            listener=listener,
            priority=priority_base,
            conditions=[
                elbv2.ListenerCondition.path_patterns(
                    [f"{path_prefix}/a", f"{path_prefix}/a/*"]
                ),
            ],
            action=elbv2.ListenerAction.forward([target_group_a]),
        )
        elbv2.ApplicationListenerRule(
            self,
            "ServiceBRoute",
            listener=listener,
            priority=priority_base + 1,
            conditions=[
                elbv2.ListenerCondition.path_patterns(
                    [f"{path_prefix}/b", f"{path_prefix}/b/*"]
                ),
            ],
            action=elbv2.ListenerAction.forward([target_group_b]),
        )
        service_security_group.connections.allow_from(
            alb_security_group, ec2.Port.tcp(8000)
        )

        CfnOutput(
            self,
            "PreviewBaseUrl",
            value=Fn.join(
                "",
                ["http://", Fn.import_value("PreviewAlbDnsName"), path_prefix],
            ),
        )

from aws_cdk import CfnParameter, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigateway as apigw_
from aws_cdk import aws_dynamodb as ddb_
from aws_cdk import aws_iam as iam_
from aws_cdk import aws_lambda as lambda_
from aws_cdk.aws_logs import LogGroup, RetentionDays
from constructs import Construct

LAMBDA_DIR = "lambda"


def get_channel_ids(settings):
    ret = []
    for v in settings["access"].values():
        if v.get("channels"):
            ret.extend(v["channels"].keys())
    return ret


def get_team_ids(settings):
    return [v["team_id"] for v in settings["access"].values() if v.get("team_id")]


class SlackAppConstructsStack(Stack):
    def __init__(self, scope: Construct, id: str, settings, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.id = id

        # cdk deploy --parameters StageName=v1
        stage = CfnParameter(
            self, "StageName",
            default="v1",
            description="The name of the API Gateway Stage.",
            type="String",
        ).value_as_string

        table_name = f"{id}-OAuth"
        ssm_param_key_verification_token = settings["ssm_parameter_key_verification_token"]

        # Create dynamodb table for oauth tokens of all app installations
        self.oauth_table = self.create_dynamodb_table(table_name)

        # Create function AsyncWorker
        self.func_async_worker = self.create_lambda("AsyncWorker", self.oauth_table.table_arn, custom_role=None)
        self.func_async_worker.add_environment("OAuthDynamoDBTable", table_name)

        # Create function SyncWorker
        self.func_sync_worker = self.create_lambda("SyncWorker", self.oauth_table.table_arn, custom_role=None)
        self.func_sync_worker.add_environment("OAuthDynamoDBTable", table_name)

        # Create function and role for ImmediateResponse
        func_immediate_response_role = self.create_immediate_response_execution_role(
            f"{id}-ImmediateResponse",
            ssm_param_key_verification_token,
            self.oauth_table.table_arn
        )
        func_immediate_response = self.create_lambda("ImmediateResponse", self.oauth_table.table_arn, func_immediate_response_role)
        func_immediate_response.add_environment("SlackAppId", settings["slack_app_id"])
        func_immediate_response.add_environment("SlackChannelIds", ",".join(get_channel_ids(settings)))
        func_immediate_response.add_environment("SlackTeamIds", ",".join(get_team_ids(settings)))
        func_immediate_response.add_environment("SlackVerificationTokenParameterKey", ssm_param_key_verification_token)
        func_immediate_response.add_environment("AsyncWorkerLambdaFunctionName", f"{id}-AsyncWorker")
        func_immediate_response.add_environment("SyncWorkerLambdaFunctionName", f"{id}-SyncWorker")
        func_immediate_response.add_environment("OAuthDynamoDBTable", table_name)

        api = apigw_.LambdaRestApi(
            self, f"{id}-API",
            description=f"{id} API",
            endpoint_configuration=apigw_.EndpointConfiguration(types=[apigw_.EndpointType.EDGE]),
            handler=func_immediate_response,
            deploy=False,
        )

        # Create APIGW Loggroup for setting retention
        LogGroup(
            self, f"{id}-API-LogGroup",
            log_group_name=f"API-Gateway-Execution-Logs_{api.rest_api_id}/{stage}",
            retention=RetentionDays.ONE_DAY,
        )

        # Do a new deployment on specific stage
        new_deployment = apigw_.Deployment(self, f"{id}-API-Deployment", api=api)
        apigw_.Stage(
            self, f"{id}-API-Stage",
            data_trace_enabled=False,
            description=f"{stage} environment",
            deployment=new_deployment,
            logging_level=apigw_.MethodLoggingLevel.ERROR,
            metrics_enabled=True,
            stage_name=stage,
            tracing_enabled=False,
        )

    def create_dynamodb_table(self, table_name: str) -> ddb_.Table:
        return ddb_.Table(
            self, table_name,
            billing_mode=ddb_.BillingMode.PAY_PER_REQUEST,
            partition_key=ddb_.Attribute(name="app_id", type=ddb_.AttributeType.STRING),
            removal_policy=RemovalPolicy.DESTROY,
            sort_key=ddb_.Attribute(name="team_id", type=ddb_.AttributeType.STRING),
            table_name=table_name,
        )

    def create_lambda(self, function_name: str, table_arn: str, custom_role: iam_.Role) -> lambda_.Function:
        if custom_role is None:
            custom_role: iam_.Role = self.create_default_role(f"{self.id}-{function_name}", table_arn)

        return lambda_.Function(
            self, f"{self.id}-{function_name}",
            code=lambda_.Code.from_asset(
                LAMBDA_DIR,
                exclude=[
                    "*.test.py",
                    "requirements.txt",
                ],
            ),
            current_version_options=lambda_.VersionOptions(
                removal_policy=RemovalPolicy.DESTROY,
                retry_attempts=2,
            ),
            function_name=f"{self.id}-{function_name}",
            handler=f"{function_name}.lambda_handler",
            log_retention=RetentionDays.ONE_DAY,
            role=custom_role,
            runtime=lambda_.Runtime.PYTHON_3_9,
            timeout=Duration.seconds(900),
            tracing=lambda_.Tracing.DISABLED,
        )

    def create_immediate_response_execution_role(self, function_name: str, parameter_key: str, table_arn: str) -> iam_.Role:
        role_name = f"{function_name}-ExecutionRole"
        return iam_.Role(
            self, role_name,
            assumed_by=iam_.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                f"{function_name}-ExecutionPolicy": iam_.PolicyDocument(
                    statements=[
                        iam_.PolicyStatement(
                            actions=[
                                "dynamodb:BatchGet*",
                                "dynamodb:Describe*",
                                "dynamodb:Get*",
                                "dynamodb:Query",
                                "dynamodb:Scan",
                            ],
                            effect=iam_.Effect.ALLOW,
                            resources=[
                                table_arn,
                            ],
                        ),
                        iam_.PolicyStatement(
                            actions=[
                                "lambda:InvokeFunction",
                                "lambda:InvokeAsync",
                            ],
                            effect=iam_.Effect.ALLOW,
                            resources=[
                                self.func_async_worker.function_arn,
                                self.func_sync_worker.function_arn,
                            ],
                        ),
                        iam_.PolicyStatement(
                            actions=[
                                "ssm:GetParameter",
                            ],
                            effect=iam_.Effect.ALLOW,
                            resources=[
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter{parameter_key}",
                            ],
                        ),
                    ]
                )
            },
            managed_policies=[
                iam_.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                # iam_.ManagedPolicy.from_aws_managed_policy_name("AWSXrayWriteOnlyAccess"),
            ],
            role_name=role_name,
        )

    def create_default_role(self, function_name: str, table_arn: str) -> iam_.Role:
        role_name = f"{function_name}-ExecutionRole"
        return iam_.Role(
            self, role_name,
            assumed_by=iam_.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                f"{function_name}-ExecutionPolicy": iam_.PolicyDocument(
                    statements=[
                        iam_.PolicyStatement(
                            actions=[
                                "dynamodb:BatchGet*",
                                "dynamodb:Describe*",
                                "dynamodb:Get*",
                                "dynamodb:Query",
                                "dynamodb:Scan",
                            ],
                            effect=iam_.Effect.ALLOW,
                            resources=[
                                table_arn,
                            ],
                        ),
                    ]
                )
            },
            managed_policies=[
                iam_.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                # iam_.ManagedPolicy.from_aws_managed_policy_name("AWSXrayWriteOnlyAccess"),
            ],
            role_name=role_name,
        )

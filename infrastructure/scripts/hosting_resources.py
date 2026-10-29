"""Private S3 origin, CloudFront HTTPS hosting, and scoped GitHub publishing role."""


def add_hosting(template):
    ref = lambda name: {"Ref": name}
    sub = lambda value: {"Fn::Sub": value}
    get = lambda name, attr: {"Fn::GetAtt": [name, attr]}
    r = template["Resources"]
    r["DashboardBucket"] = {
        "Type": "AWS::S3::Bucket", "DeletionPolicy": "Retain", "UpdateReplacePolicy": "Retain",
        "Properties": {
            "PublicAccessBlockConfiguration": {"BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True},
            "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
            "BucketEncryption": {"ServerSideEncryptionConfiguration": [{"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},
        },
    }
    r["DashboardOriginAccess"] = {
        "Type": "AWS::CloudFront::OriginAccessControl",
        "Properties": {"OriginAccessControlConfig": {"Name": sub("${AWS::StackName}-dashboard"), "OriginAccessControlOriginType": "s3", "SigningBehavior": "always", "SigningProtocol": "sigv4"}},
    }
    r["DashboardCachePolicy"] = {
        "Type": "AWS::CloudFront::CachePolicy",
        "Properties": {"CachePolicyConfig": {
            "Name": sub("${AWS::StackName}-dashboard-cache"), "MinTTL": 0, "DefaultTTL": 60, "MaxTTL": 31536000,
            "ParametersInCacheKeyAndForwardedToOrigin": {"EnableAcceptEncodingGzip": True, "EnableAcceptEncodingBrotli": True, "CookiesConfig": {"CookieBehavior": "none"}, "HeadersConfig": {"HeaderBehavior": "none"}, "QueryStringsConfig": {"QueryStringBehavior": "none"}},
        }},
    }
    r["DashboardResponseHeaders"] = {
        "Type": "AWS::CloudFront::ResponseHeadersPolicy",
        "Properties": {"ResponseHeadersPolicyConfig": {
            "Name": sub("${AWS::StackName}-dashboard-security"),
            "SecurityHeadersConfig": {
                "ContentTypeOptions": {"Override": True},
                "FrameOptions": {"FrameOption": "DENY", "Override": True},
                "ReferrerPolicy": {"ReferrerPolicy": "strict-origin-when-cross-origin", "Override": True},
                "StrictTransportSecurity": {"AccessControlMaxAgeSec": 31536000, "Override": True},
                "ContentSecurityPolicy": {"Override": True, "ContentSecurityPolicy": "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self' https://*.execute-api.us-east-1.amazonaws.com https://cognito-idp.us-east-1.amazonaws.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; upgrade-insecure-requests"},
            },
        }},
    }
    r["DashboardDistribution"] = {
        "Type": "AWS::CloudFront::Distribution",
        "Properties": {"DistributionConfig": {
            "Enabled": True, "Comment": "DeployIQ dashboard", "DefaultRootObject": "index.html",
            "HttpVersion": "http2", "PriceClass": "PriceClass_100",
            "Origins": [{"Id": "DashboardS3", "DomainName": get("DashboardBucket", "RegionalDomainName"), "OriginAccessControlId": ref("DashboardOriginAccess"), "S3OriginConfig": {"OriginAccessIdentity": ""}}],
            "DefaultCacheBehavior": {"TargetOriginId": "DashboardS3", "ViewerProtocolPolicy": "redirect-to-https", "AllowedMethods": ["GET", "HEAD"], "CachedMethods": ["GET", "HEAD"], "Compress": True, "CachePolicyId": ref("DashboardCachePolicy"), "ResponseHeadersPolicyId": ref("DashboardResponseHeaders")},
            "ViewerCertificate": {"CloudFrontDefaultCertificate": True},
        }},
    }
    r["DashboardBucketPolicy"] = {
        "Type": "AWS::S3::BucketPolicy",
        "Properties": {"Bucket": ref("DashboardBucket"), "PolicyDocument": {"Version": "2012-10-17", "Statement": [
            {"Sid": "AllowOnlyThisCloudFrontOrigin", "Effect": "Allow", "Principal": {"Service": "cloudfront.amazonaws.com"}, "Action": "s3:GetObject", "Resource": sub("${DashboardBucket.Arn}/*"), "Condition": {"StringEquals": {"AWS:SourceArn": sub("arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${DashboardDistribution}")}}},
            {"Sid": "DenyInsecureTransport", "Effect": "Deny", "Principal": "*", "Action": "s3:*", "Resource": [get("DashboardBucket", "Arn"), sub("${DashboardBucket.Arn}/*")], "Condition": {"Bool": {"aws:SecureTransport": "false"}}},
        ]}},
    }
    r["DashboardPublishRole"] = {
        "Type": "AWS::IAM::Role",
        "Properties": {
            "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Federated": sub("arn:${AWS::Partition}:iam::${AWS::AccountId}:oidc-provider/token.actions.githubusercontent.com")}, "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com", "token.actions.githubusercontent.com:sub": "repo:hardikahujaa@255485039/deployiq@1437658122:ref:refs/heads/main"}}}]},
            "Policies": [{"PolicyName": "PublishDashboard", "PolicyDocument": {"Version": "2012-10-17", "Statement": [
                {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": get("DashboardBucket", "Arn")},
                {"Effect": "Allow", "Action": "s3:PutObject", "Resource": sub("${DashboardBucket.Arn}/*")},
                {"Effect": "Allow", "Action": "cloudfront:CreateInvalidation", "Resource": sub("arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${DashboardDistribution}")},
            ]}}],
        },
    }
    # Preserve the existing local origin while also accepting the deployed website.
    r["WebhookApi"]["Properties"]["CorsConfiguration"]["AllowOrigins"].append(sub("https://${DashboardDistribution.DomainName}"))
    template["Outputs"].update({
        "DashboardUrl": {"Value": sub("https://${DashboardDistribution.DomainName}")},
        "DashboardBucketName": {"Value": ref("DashboardBucket")},
        "DashboardDistributionId": {"Value": ref("DashboardDistribution")},
        "DashboardPublishRoleArn": {"Value": get("DashboardPublishRole", "Arn")},
    })
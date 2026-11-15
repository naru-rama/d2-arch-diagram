"""公式アイコン配布物のファイル名から、図のソースで使う短い名前の索引を作る。

Arch_AWS-Lambda_48.svg -> lambda
Res_Amazon-VPC_NAT-Gateway_48.svg -> vpc-nat-gateway
Res_Users_48_Light.svg -> users
k8s/pod.svg -> k8s-pod
"""
import os
import re

ALIASES = {
    "s3": "simple-storage-service",
    "sqs": "simple-queue-service",
    "sns": "simple-notification-service",
    "ses": "simple-email-service",
    "ecs": "elastic-container-service",
    "eks": "elastic-kubernetes-service",
    "ecr": "elastic-container-registry",
    "efs": "efs",
    "ebs": "elastic-block-store",
    "alb": "elastic-load-balancing-application-load-balancer",
    "nlb": "elastic-load-balancing-network-load-balancer",
    "elb": "elastic-load-balancing",
    "apigw": "api-gateway",
    "kms": "key-management-service",
    "nat-gateway": "vpc-nat-gateway",
    "igw": "vpc-internet-gateway",
    "internet-gateway": "vpc-internet-gateway",
    "internet": "internet-alt1",
    "k8s-deployment": "k8s-deploy",
    "k8s-service": "k8s-svc",
    "k8s-ingress": "k8s-ing",
    "k8s-namespace": "k8s-ns",
    "k8s-statefulset": "k8s-sts",
    "k8s-daemonset": "k8s-ds",
    "k8s-replicaset": "k8s-rs",
    "k8s-configmap": "k8s-cm",
    "k8s-serviceaccount": "k8s-sa",
    "k8s-persistentvolume": "k8s-pv",
    "k8s-persistentvolumeclaim": "k8s-pvc",
    "k8s-storageclass": "k8s-sc",
    "k8s-networkpolicy": "k8s-netpol",
    "k8s-endpoints": "k8s-ep",
}

GROUP_FILES = {
    "aws-cloud": "AWS-Cloud-logo_32.svg",
    "region": "Region_32.svg",
    "vpc": "Virtual-private-cloud-VPC_32.svg",
    "public-subnet": "Public-subnet_32.svg",
    "private-subnet": "Private-subnet_32.svg",
    "account": "AWS-Account_32.svg",
    "auto-scaling-group": "Auto-Scaling-group_32.svg",
    "corporate-data-center": "Corporate-data-center_32.svg",
    "server-contents": "Server-contents_32.svg",
    "ec2-instance-contents": "EC2-instance-contents_32.svg",
    "spot-fleet": "Spot-Fleet_32.svg",
    "k8s-cluster": "k8s/control-plane.svg",
    "k8s-namespace": "k8s/ns.svg",
    "k8s-node": "k8s/node.svg",
    "k8s-pod": "k8s/pod.svg",
    "k8s-deployment": "k8s/deploy.svg",
}


def slug(text):
    text = re.sub(r"^(AWS|Amazon)-", "", text)
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def key_of(filename):
    name = filename[:-4]
    name = re.sub(r"_(48|32)(_Light)?$", "", name)
    if name.startswith("Arch_"):
        return slug(name[5:]), 0
    if name.startswith("Res_"):
        parts = name[4:].split("_", 1)
        service = slug(parts[0])
        if len(parts) == 1:
            return service, 1
        resource = slug(parts[1])
        if resource.startswith(service + "-") or resource == service:
            return resource, 1
        return f"{service}-{resource}", 1
    return None, 9


def build(icon_dir):
    found = {}
    for filename in sorted(os.listdir(icon_dir)):
        if not filename.endswith(".svg"):
            continue
        key, rank = key_of(filename)
        if key and (key not in found or rank < found[key][0]):
            found[key] = (rank, filename)
    table = {k: v[1] for k, v in found.items()}
    k8s_dir = os.path.join(icon_dir, "k8s")
    if os.path.isdir(k8s_dir):
        for filename in sorted(os.listdir(k8s_dir)):
            if filename.endswith(".svg"):
                table[f"k8s-{filename[:-4]}"] = f"k8s/{filename}"
    for alias, target in ALIASES.items():
        if target in table and alias not in table:
            table[alias] = table[target]
    return table

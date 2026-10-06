"""Generate static project manifests containing secret references, never values."""
import argparse
import json
import re
from pathlib import Path


def secret_env(name, key, secret):
    return {'name': name, 'valueFrom': {'secretKeyRef': {'name': secret, 'key': key}}}


def db_env(secret):
    return [secret_env(key, key, secret) for key in ('PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--namespace', default='default')
    parser.add_argument('--profile', choices=['local', 'deploy'], default='local')
    parser.add_argument('--backend-image', default='kedrogy-registry:5000/mysite:dev')
    parser.add_argument('--web-image', default='kedrogy-registry:5000/web:dev')
    parser.add_argument('--app-host')
    parser.add_argument('--label-host')
    parser.add_argument('--tls-secret')
    parser.add_argument('--trusted-proxy-cidrs')
    parser.add_argument('--output-dir', type=Path, default=Path('.'))
    args = parser.parse_args()
    deploy = args.profile == 'deploy'
    args.app_host = args.app_host or ('app.kedrogy.test' if deploy else 'app.localhost')
    args.label_host = args.label_host or ('label.kedrogy.test' if deploy else 'label.localhost')
    if deploy and (not args.tls_secret or not args.trusted_proxy_cidrs):
        parser.error('Deploy requires --tls-secret and --trusted-proxy-cidrs.')
    if deploy and any(not re.fullmatch(r'[^ ]+@sha256:[a-f0-9]{64}', image)
                      for image in [args.backend_image, args.web_image]):
        parser.error('Deploy requires immutable backend and web image digests.')
    if args.app_host == args.label_host or any(not re.fullmatch(r'[a-z0-9]+[a-z0-9.-]*[a-z0-9]', host)
                                              for host in [args.app_host, args.label_host]):
        parser.error('Use two different explicit DNS hostnames.')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    def write(name, items):
        path = args.output_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'apiVersion': 'v1', 'kind': 'List', 'items': items}, indent=2) + '\n')
    profile = {'DJANGO_SETTINGS_MODULE': f'mysite.settings_{args.profile}', 'DJANGO_DEBUG': 'false',
               'KEDROGY_ANNOTATION_URL': f'{"https" if deploy else "http"}://{args.label_host}{"" if deploy else ":8081"}',
               'DJANGO_ALLOWED_HOSTS': args.app_host if deploy else f'localhost,127.0.0.1,{args.app_host}',
               'DJANGO_CORS_ORIGINS': f'{"https" if deploy else "http"}://{args.app_host}',
               'DJANGO_CSRF_ORIGINS': f'{"https" if deploy else "http"}://{args.app_host}',
               'DJANGO_TRUSTED_PROXY_CIDRS': args.trusted_proxy_cidrs or ''}
    profile_env = [{'name': key, 'value': value} for key, value in profile.items()]
    profile_env.append({'name': 'KEDROGY_NAMESPACE', 'valueFrom': {'fieldRef': {'fieldPath': 'metadata.namespace'}}})
    reader_env = [secret_env('READER_' + key, key, 'kedrogy-db-reader') for key in ('PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD')]
    app_env = profile_env + db_env('kedrogy-db-app') + reader_env + [secret_env(key, key, 'kedrogy-app-config') for key in ('DJANGO_SECRET_KEY', 'KEDROGY_ML_IMAGE')]
    alias_env = secret_env('KEDROGY_ML_IMAGE_ALIASES', 'KEDROGY_ML_IMAGE_ALIASES', 'kedrogy-app-config')
    alias_env['valueFrom']['secretKeyRef']['optional'] = True
    app_env.append(alias_env)
    image = args.backend_image
    sa = [{'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {'name': name}, 'automountServiceAccountToken': name == 'kedrogy-controller'}
          for name in ('kedrogy-controller', 'kedrogy-workload')]
    role = {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'Role', 'metadata': {'name': 'kedrogy-controller'}, 'rules': [
        {'apiGroups': [''], 'resources': ['configmaps', 'persistentvolumeclaims', 'services'], 'verbs': ['get', 'list', 'watch', 'create', 'patch', 'update', 'delete']},
        {'apiGroups': ['apps'], 'resources': ['deployments'], 'verbs': ['get', 'list', 'watch', 'create', 'patch', 'update', 'delete']},
        {'apiGroups': ['apps'], 'resources': ['replicasets', 'statefulsets', 'daemonsets'], 'verbs': ['get', 'list']},
        {'apiGroups': ['batch'], 'resources': ['cronjobs'], 'verbs': ['get', 'list']},
        {'apiGroups': ['batch'], 'resources': ['jobs'], 'verbs': ['get', 'list', 'watch', 'create', 'patch', 'update', 'delete']},
        {'apiGroups': [''], 'resources': ['pods', 'pods/log'], 'verbs': ['get', 'list', 'watch']},
        {'apiGroups': [''], 'resources': ['pods/portforward'], 'verbs': ['create']},
    ]}
    binding = {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'RoleBinding', 'metadata': {'name': 'kedrogy-controller'},
               'subjects': [{'kind': 'ServiceAccount', 'name': 'kedrogy-controller'}],
               'roleRef': {'kind': 'Role', 'name': 'kedrogy-controller', 'apiGroup': 'rbac.authorization.k8s.io'}}
    identity_role = {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'ClusterRole',
        'metadata': {'name': f'kedrogy-namespace-identity-{args.namespace}'}, 'rules': [
            {'apiGroups': [''], 'resources': ['namespaces'], 'resourceNames': [args.namespace], 'verbs': ['get']}]}
    identity_binding = {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'ClusterRoleBinding',
        'metadata': {'name': f'kedrogy-namespace-identity-{args.namespace}'},
        'subjects': [{'kind': 'ServiceAccount', 'name': 'kedrogy-controller', 'namespace': args.namespace}],
        'roleRef': {'kind': 'ClusterRole', 'name': identity_role['metadata']['name'], 'apiGroup': 'rbac.authorization.k8s.io'}}
    labels = {'app.kubernetes.io/name': 'mysite'}
    deployment = {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': 'mysite'}, 'spec': {'replicas': 1,
        'selector': {'matchLabels': labels}, 'template': {'metadata': {'labels': labels}, 'spec': {
            'serviceAccountName': 'kedrogy-controller',
            'initContainers': [
                {'name': 'migrate', 'image': image, 'args': ['-m', 'django', 'migrate', '--settings', profile['DJANGO_SETTINGS_MODULE']],
                 'env': profile_env + db_env('kedrogy-db-migrator') + [secret_env(key, key, 'kedrogy-app-config') for key in ('DJANGO_SECRET_KEY', 'KEDROGY_ML_IMAGE')]},
                {'name': 'db-worker', 'image': image, 'restartPolicy': 'Always',
                 'args': ['-m', 'django', 'db_worker', '--settings', profile['DJANGO_SETTINGS_MODULE'], '--no-reload'], 'env': app_env},
                {'name': 'training-reconciler', 'image': image, 'restartPolicy': 'Always',
                 'args': ['-m', 'django', 'reconcile_training', '--watch'], 'env': app_env},
                {'name': 'serving-reconciler', 'image': image, 'restartPolicy': 'Always',
                 'args': ['-m', 'django', 'reconcile_serving', '--watch'], 'env': app_env},
                {'name': 'operation-reconciler', 'image': image, 'restartPolicy': 'Always',
                 'args': ['-m', 'django', 'reconcile_operations', '--watch'], 'env': app_env}],
            'containers': [{'name': 'mysite', 'image': image,
                            'args': ['-m', 'uvicorn', 'mysite.asgi:application', '--host', '0.0.0.0', '--port', '8000', '--no-proxy-headers'],
                            'env': app_env, 'ports': [{'containerPort': 8000}],
                            'readinessProbe': {'httpGet': {'path': '/health/', 'port': 8000, 'httpHeaders': [{'name': 'Host', 'value': args.app_host}]}, 'initialDelaySeconds': 3},
                            'livenessProbe': {'httpGet': {'path': '/health/', 'port': 8000, 'httpHeaders': [{'name': 'Host', 'value': args.app_host}]}, 'initialDelaySeconds': 15}}]}}}}
    svc = {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'mysite-svc'},
           'spec': {'selector': labels, 'ports': [{'name': 'uvicorn', 'port': 8000, 'targetPort': 8000}]}}
    write('mysite.yaml', [*sa, role, binding, identity_role, identity_binding, deployment, svc])
    write('infra/rbac.json', [*sa, role, binding, identity_role, identity_binding])
    labels = {'app': 'postgres'}
    pg_env = [secret_env(key, key, 'kedrogy-db-admin') for key in ('PGPORT', 'PGUSER', 'PGPASSWORD')]
    pg_env += [secret_env('POSTGRES_USER', 'PGUSER', 'kedrogy-db-admin'), secret_env('POSTGRES_PASSWORD', 'PGPASSWORD', 'kedrogy-db-admin'), secret_env('POSTGRES_DB', 'PGDATABASE', 'kedrogy-db-admin')]
    postgres = [
        {'apiVersion': 'v1', 'kind': 'PersistentVolumeClaim', 'metadata': {'name': 'postgres-pvc', 'labels': labels},
         'spec': {'accessModes': ['ReadWriteOnce'], 'resources': {'requests': {'storage': '1Gi'}}}},
        {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': 'postgres-deployment', 'labels': labels},
         'spec': {'replicas': 1, 'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': labels},
                  'template': {'metadata': {'labels': labels}, 'spec': {'automountServiceAccountToken': False,
                      'containers': [{'name': 'postgres', 'image': 'postgres:18', 'env': pg_env,
                                      'ports': [{'containerPort': 30001}], 'volumeMounts': [{'name': 'postgres-volume', 'mountPath': '/var/lib/postgresql'}]}],
                      'volumes': [{'name': 'postgres-volume', 'persistentVolumeClaim': {'claimName': 'postgres-pvc'}}]}}}},
        {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'postgres-svc', 'labels': labels},
         'spec': {'type': 'ClusterIP' if deploy else 'LoadBalancer', 'selector': labels, 'ports': [{'port': 30001, 'targetPort': 30001}]}}
    ]
    write('postgres.yaml', postgres)
    write('infra/web.json', web_resources(args, deploy))


def web_resources(args, deploy):
    """Route explicit application/annotation hosts through a constrained proxy."""
    selector = {'app.kubernetes.io/name': 'kedrogy-web'}
    proxy = Path('infra/nginx-proxy.conf').read_text()
    if deploy:
        # Only the TLS ingress may reach this web service (NetworkPolicy below).
        proxy = proxy.replace('X-Forwarded-Proto http;', 'X-Forwarded-Proto https;')
    config = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'kedrogy-web'},
              'data': {'default.conf': Path('infra/nginx.conf').read_text(), 'proxy.conf': proxy}}
    web = {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': 'kedrogy-web'},
           'spec': {'replicas': 1, 'selector': {'matchLabels': selector}, 'template': {
               'metadata': {'labels': selector}, 'spec': {'automountServiceAccountToken': False,
                   'containers': [{'name': 'web', 'image': args.web_image, 'ports': [{'containerPort': 8080}],
                       'readinessProbe': {'httpGet': {'path': '/', 'port': 8080}},
                       'volumeMounts': [
                           {'name': 'config', 'mountPath': '/etc/nginx/conf.d/default.conf', 'subPath': 'default.conf'},
                           {'name': 'config', 'mountPath': '/etc/nginx/proxy_params_kedrogy', 'subPath': 'proxy.conf'}]}],
                   'volumes': [{'name': 'config', 'configMap': {'name': 'kedrogy-web'}}]}}}}
    resources = [config, web]
    for name, labels, port in [('kedrogy-web', selector, 8080), ('prodigy-svc', {'app.kubernetes.io/name': 'prodigy'}, 8080)]:
        resources.append({'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': name},
                          'spec': {'selector': labels, 'ports': [{'port': port, 'targetPort': port}]}})
    rules = [{'host': host, 'http': {'paths': [{'path': '/', 'pathType': 'Prefix', 'backend': {
        'service': {'name': service, 'port': {'number': 8080}}}}]}}
        for host, service in [(args.app_host, 'kedrogy-web'), (args.label_host, 'prodigy-svc')]]
    ingress = {'apiVersion': 'networking.k8s.io/v1', 'kind': 'Ingress', 'metadata': {'name': 'kedrogy'},
               'spec': {'ingressClassName': 'traefik', 'rules': rules}}
    if deploy:
        ingress['spec']['tls'] = [{'hosts': [args.app_host, args.label_host], 'secretName': args.tls_secret}]
        ingress['metadata']['annotations'] = {'traefik.ingress.kubernetes.io/router.entrypoints': 'websecure',
                                               'traefik.ingress.kubernetes.io/router.tls': 'true'}
        resources.append({'apiVersion': 'traefik.io/v1alpha1', 'kind': 'Middleware',
                          'metadata': {'name': 'kedrogy-https'}, 'spec': {'redirectScheme': {'scheme': 'https', 'permanent': True}}})
        # Namespace is substituted by kubectl/kustomize using this argument-free router configuration.
        resources.append({'apiVersion': 'traefik.io/v1alpha1', 'kind': 'IngressRoute',
            'metadata': {'name': 'kedrogy-http'}, 'spec': {'entryPoints': ['web'], 'routes': [
                {'kind': 'Rule', 'match': f'Host(`{host}`)', 'middlewares': [{'name': 'kedrogy-https'}],
                 'services': [{'name': service, 'port': 8080}]}
                for host, service in [(args.app_host, 'kedrogy-web'), (args.label_host, 'prodigy-svc')]]}})
        ingress_peer = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                        'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'traefik'}}}
        for name, labels, port, peers in [
            ('mysite-ingress', {'app.kubernetes.io/name': 'mysite'}, 8000, [{'podSelector': {'matchLabels': selector}}]),
            ('web-ingress', selector, 8080, [ingress_peer]),
            ('prodigy-ingress', {'app.kubernetes.io/name': 'prodigy'}, 8080, [ingress_peer]),
            ('annotation-health', {'app.kubernetes.io/name': 'prodigy'}, 8081,
             [{'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'mysite'}}}]),
        ]:
            resources.append({'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy', 'metadata': {'name': name},
                'spec': {'podSelector': {'matchLabels': labels}, 'policyTypes': ['Ingress'],
                         'ingress': [{'from': peers, 'ports': [{'protocol': 'TCP', 'port': port}]}]}})
    resources.append(ingress)
    return resources


if __name__ == '__main__':
    main()

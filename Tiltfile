docker_build('lts-registry.localhost:5500/mysite:latest', 
             '.',
             dockerfile='Dockerfile',
             build_args={
                'UV_INDEX_PRODIGY_USERNAME': os.environ.get('UV_INDEX_PRODIGY_USERNAME', ''),
                'UV_INDEX_YSZ_USERNAME': os.environ.get('UV_INDEX_YSZ_USERNAME', ''),
                'UV_INDEX_YSZ_PASSWORD': os.environ.get('UV_INDEX_YSZ_PASSWORD', ''),
             },
    live_update=[
        sync('.', '/app'),
        # run('cd /app && pip install -r requirements.txt',
        #     trigger='./requirements.txt'),
])             
k8s_yaml('mysite.yaml')
#k8s_resource('mysite-svc', port_forwards=8000)#use ingress instead 

docker_build('lts-registry.localhost:5500/mysite:latest', 
             '.',
             dockerfile='Dockerfile',
             build_args={'UV_INDEX_PRODIGY_USERNAME': os.environ.get('UV_INDEX_PRODIGY_USERNAME', '')},
    live_update=[
        sync('.', '/app'),
        # run('cd /app && pip install -r requirements.txt',
        #     trigger='./requirements.txt'),
])             
k8s_yaml('mysite.yaml')
k8s_resource('mysite', port_forwards=8000)

from django.core.files.storage import Storage
from fdfs_client.client import Fdfs_client, get_tracker_conf
from django.conf import settings


class FDFSStorage(Storage):
    '''fast dfs文件存储类'''

    def __init__(self, fdfs_clientConf=None, fdfs_nginx_url=None):
        if fdfs_clientConf is None:
            # fdfs_clientConf = settings.FDFS_CLIENT_CONF
            fdfs_clientConf = get_tracker_conf(r'E:\workspace\fresh\utils\fdfs\client.conf')
        self.fdfs_clientConf = fdfs_clientConf

        if fdfs_nginx_url is None:
            fdfs_nginx_url = settings.FDFS_BASE_URL
        self.fdfs_nginx_url = fdfs_nginx_url

    def _open(self, name, mode='rb'):
        '''打开文件时使用'''
        pass

    def _save(self, name, content, max_length=None):
        '''保存文件时使用'''
        # name:选择上传文件的名字
        # content:上传的文件的File对象

        # 创建一个Fdfs_client对象
        client = Fdfs_client(self.fdfs_clientConf)

        # 创建文件到fast dfs系统中, 通过文件内容上传，返回一个字典类型ret
        res = client.upload_by_buffer(content.read())

        # dict
        # {
        #   'Group name': group_name,
        #   'Remote file_id': remote_file_id,
        #   'Status': 'Upload successed.',
        #   'Local file name': '',
        #   'Uploaded size': upload_size,
        #   'Storage IP': storage_ip
        # }

        if res.get('Status') != 'Upload successed.':
            # 上传失败
            raise Exception('上传文件到fast dfs失败')

        # 获取返回的文件id
        filename = res.get('Remote file_id')
        return filename.decode()

    def exists(self, name):
        '''Django判断文件名是否可用'''

        return False

    def url(self, name):
        '''返回访问文件的url路径'''

        return self.fdfs_nginx_url + name

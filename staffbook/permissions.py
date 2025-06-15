#也可以直接把它写在 staffbook/views.py 文件的顶部（import区下方）——但长远看推荐专门放权限相关逻辑的文件。
def is_staffbook_admin(user):
    return user.is_authenticated and hasattr(user, 'userprofile') and user.userprofile.is_staffbook_admin
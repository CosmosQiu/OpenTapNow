import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown, Folder, Layers, Loader2, LogOut, Plus, Trash2, User, X } from 'lucide-react';

const fallbackLocalServerUrl = () => {
    try {
        return (localStorage.getItem('tapnow_local_server_url') || 'http://127.0.0.1:9527').replace(/\/+$/, '');
    } catch {
        return 'http://127.0.0.1:9527';
    }
};

const resolveLocalServerUrl = (getLocalServerUrl) => {
    if (typeof getLocalServerUrl === 'function') {
        return getLocalServerUrl();
    }
    return fallbackLocalServerUrl();
};

export const LoginModal = ({ isOpen, onClose, onLogin, theme, getLocalServerUrl }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        try {
            const baseUrl = resolveLocalServerUrl(getLocalServerUrl);
            const res = await fetch(`${baseUrl}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });

            const data = await res.json();
            if (res.ok && data.success) {
                localStorage.setItem('tapnow_auth_token', data.token);
                onLogin(data.user);
                onClose();
            } else {
                setError(data.message || '登录失败');
            }
        } catch (e2) {
            setError('无法连接到服务器');
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    const isDark = theme === 'dark';
    const isSolarized = theme === 'solarized';

    return (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div
                className={`w-full max-w-md p-6 rounded-2xl border shadow-2xl ${isDark
                    ? 'bg-zinc-900 border-zinc-700 text-zinc-200'
                    : isSolarized
                        ? 'bg-[#fdf6e3] border-[#d7cfb2] text-[#586e75]'
                        : 'bg-white border-zinc-300 text-zinc-800'
                    }`}
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-xl font-bold">登录</h2>
                    <button onClick={onClose} className="p-1 rounded hover:bg-zinc-700/50">
                        <X size={20} />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                    {error && (
                        <div className="p-3 rounded-lg bg-red-900/30 border border-red-800 text-red-200 text-sm">
                            {error}
                        </div>
                    )}

                    <div>
                        <label className="block text-sm font-medium mb-1.5">用户名</label>
                        <input
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className={`w-full px-3 py-2 rounded-lg border text-sm ${isDark
                                ? 'bg-zinc-800 border-zinc-700 text-zinc-200'
                                : 'bg-white border-zinc-300 text-zinc-800'
                                }`}
                            placeholder="请输入用户名"
                            disabled={loading}
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1.5">密码</label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className={`w-full px-3 py-2 rounded-lg border text-sm ${isDark
                                ? 'bg-zinc-800 border-zinc-700 text-zinc-200'
                                : 'bg-white border-zinc-300 text-zinc-800'
                                }`}
                            placeholder="请输入密码"
                            disabled={loading}
                        />
                    </div>

                    <button
                        type="submit"
                        disabled={loading || !username || !password}
                        className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                        {loading ? <Loader2 size={18} className="animate-spin" /> : null}
                        {loading ? '登录中...' : '登录'}
                    </button>
                </form>
            </div>
        </div>
    );
};

export const LoginScreen = ({ onLogin, theme, getLocalServerUrl }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const isDark = theme === 'dark';
    const isSolarized = theme === 'solarized';

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        try {
            const baseUrl = resolveLocalServerUrl(getLocalServerUrl);
            const res = await fetch(`${baseUrl}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                localStorage.setItem('tapnow_auth_token', data.token);
                onLogin(data.user);
                return;
            }
            setError(data.error || data.message || '登录失败');
        } catch (e2) {
            setError('无法连接到服务器');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className={`w-full h-screen flex items-center justify-center px-4 ${isDark
            ? 'bg-[#09090b] text-zinc-100'
            : isSolarized
                ? 'bg-[#fdf6e3] text-[#586e75]'
                : 'bg-zinc-100 text-zinc-900'
            }`}>
            <div className={`w-full max-w-md p-6 rounded-2xl border shadow-2xl ${isDark
                ? 'bg-zinc-900 border-zinc-700'
                : isSolarized
                    ? 'bg-[#eee8d5] border-[#d7cfb2]'
                    : 'bg-white border-zinc-300'
                }`}>
                <div className="flex items-center gap-3 mb-6">
                    <div className="w-9 h-9 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-md flex items-center justify-center">
                        <Layers size={18} className="text-white" />
                    </div>
                    <div>
                        <h1 className="text-lg font-bold">Tapnow Studio</h1>
                        <p className="text-xs text-zinc-500">请登录后继续</p>
                    </div>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    {error ? (
                        <div className="p-3 rounded-lg bg-red-900/30 border border-red-800 text-red-200 text-sm">{error}</div>
                    ) : null}
                    <input
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        placeholder="用户名"
                        className={`w-full px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-zinc-800 border-zinc-700 text-zinc-200' : 'bg-white border-zinc-300 text-zinc-800'}`}
                        disabled={loading}
                    />
                    <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="密码"
                        className={`w-full px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-zinc-800 border-zinc-700 text-zinc-200' : 'bg-white border-zinc-300 text-zinc-800'}`}
                        disabled={loading}
                    />
                    <button
                        type="submit"
                        disabled={loading || !username || !password}
                        className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
                    >
                        {loading ? '登录中...' : '登录并进入 Studio'}
                    </button>
                </form>
            </div>
        </div>
    );
};

export const AdminUserManagementModal = ({ isOpen, onClose, theme, getLocalServerUrl }) => {
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [username, setUsername] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [password, setPassword] = useState('');
    const isDark = theme === 'dark';

    const loadUsers = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const baseUrl = resolveLocalServerUrl(getLocalServerUrl);
            const token = localStorage.getItem('tapnow_auth_token') || '';
            const res = await fetch(`${baseUrl}/admin/users`, {
                headers: token ? { Authorization: `Bearer ${token}` } : {}
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error || '加载用户失败');
            }
            setUsers(data.users || []);
        } catch (e2) {
            setError(e2.message || '加载用户失败');
        } finally {
            setLoading(false);
        }
    }, [getLocalServerUrl]);

    useEffect(() => {
        if (isOpen) loadUsers();
    }, [isOpen, loadUsers]);

    const handleCreateUser = async (e) => {
        e.preventDefault();
        if (!username.trim() || !password) return;
        setError('');
        try {
            const baseUrl = resolveLocalServerUrl(getLocalServerUrl);
            const token = localStorage.getItem('tapnow_auth_token') || '';
            const res = await fetch(`${baseUrl}/admin/users`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: `Bearer ${token}` } : {})
                },
                body: JSON.stringify({ username: username.trim(), display_name: displayName.trim(), password })
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.error || '创建用户失败');
            setUsername('');
            setDisplayName('');
            setPassword('');
            await loadUsers();
        } catch (e2) {
            setError(e2.message || '创建用户失败');
        }
    };

    const handleResetPassword = async (userId, usernameText) => {
        const newPassword = window.prompt(`请输入用户 ${usernameText} 的新密码`);
        if (!newPassword) return;
        setError('');
        try {
            const baseUrl = resolveLocalServerUrl(getLocalServerUrl);
            const token = localStorage.getItem('tapnow_auth_token') || '';
            const res = await fetch(`${baseUrl}/admin/users/${userId}/password`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: `Bearer ${token}` } : {})
                },
                body: JSON.stringify({ new_password: newPassword })
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.error || '修改密码失败');
            await loadUsers();
        } catch (e2) {
            setError(e2.message || '修改密码失败');
        }
    };

    const handleDeleteUser = async (userId, usernameText) => {
        if (!window.confirm(`确定删除用户 ${usernameText} ?`)) return;
        setError('');
        try {
            const baseUrl = resolveLocalServerUrl(getLocalServerUrl);
            const token = localStorage.getItem('tapnow_auth_token') || '';
            const res = await fetch(`${baseUrl}/admin/users/${userId}`, {
                method: 'DELETE',
                headers: token ? { Authorization: `Bearer ${token}` } : {}
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.error || '删除用户失败');
            await loadUsers();
        } catch (e2) {
            setError(e2.message || '删除用户失败');
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className={`w-full max-w-2xl max-h-[80vh] overflow-hidden rounded-2xl border shadow-2xl flex flex-col ${isDark ? 'bg-zinc-900 border-zinc-700 text-zinc-200' : 'bg-white border-zinc-300 text-zinc-800'}`}>
                <div className="flex items-center justify-between p-4 border-b border-zinc-700/50">
                    <h2 className="text-lg font-bold">管理后台 · 用户管理</h2>
                    <button onClick={onClose} className="p-1 rounded hover:bg-zinc-700/50"><X size={18} /></button>
                </div>
                <div className="p-4 border-b border-zinc-700/50">
                    <form onSubmit={handleCreateUser} className="grid grid-cols-1 md:grid-cols-4 gap-2">
                        <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="用户名" className={`px-3 py-2 rounded border text-sm ${isDark ? 'bg-zinc-800 border-zinc-700' : 'bg-white border-zinc-300'}`} />
                        <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="显示名称(可选)" className={`px-3 py-2 rounded border text-sm ${isDark ? 'bg-zinc-800 border-zinc-700' : 'bg-white border-zinc-300'}`} />
                        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="初始密码" className={`px-3 py-2 rounded border text-sm ${isDark ? 'bg-zinc-800 border-zinc-700' : 'bg-white border-zinc-300'}`} />
                        <button type="submit" className="px-3 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white text-sm">新增用户</button>
                    </form>
                    {error ? <div className="mt-2 text-xs text-red-400">{error}</div> : null}
                </div>
                <div className="p-4 overflow-auto">
                    {loading ? (
                        <div className="text-sm text-zinc-500">加载中...</div>
                    ) : (
                        <div className="space-y-2">
                            {users.map((u) => (
                                <div key={u.id} className={`p-3 rounded-lg border flex items-center justify-between ${isDark ? 'border-zinc-700 bg-zinc-800/40' : 'border-zinc-200 bg-zinc-50'}`}>
                                    <div>
                                        <div className="text-sm font-medium">{u.display_name || u.username}</div>
                                        <div className="text-xs text-zinc-500">{u.username}{u.is_admin ? ' · 管理员' : ''}</div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <button onClick={() => handleResetPassword(u.id, u.username)} className="px-2 py-1 rounded border text-xs hover:bg-zinc-700/50">改密码</button>
                                        {!u.is_admin ? (
                                            <button onClick={() => handleDeleteUser(u.id, u.username)} className="px-2 py-1 rounded border border-red-700 text-red-400 text-xs hover:bg-red-900/30">删除</button>
                                        ) : null}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export const ProjectSelector = ({ project, onClick, theme }) => {
    const isDark = theme === 'dark';

    return (
        <button
            onClick={onClick}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all ${isDark
                ? 'bg-zinc-800 border-zinc-700 hover:border-zinc-600 text-zinc-200'
                : 'bg-white border-zinc-300 hover:border-zinc-400 text-zinc-800'
                }`}
        >
            <Folder size={16} className="text-blue-500" />
            <span className="text-sm font-medium max-w-[150px] truncate">
                {project?.name || '选择项目'}
            </span>
            <ChevronDown size={14} className="text-zinc-500" />
        </button>
    );
};

export const UserMenu = ({ user, onLoginClick, onLogout, theme }) => {
    const [isOpen, setIsOpen] = useState(false);
    const menuRef = useRef(null);
    const isDark = theme === 'dark';

    useEffect(() => {
        const handleClickOutside = (e) => {
            if (menuRef.current && !menuRef.current.contains(e.target)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    if (!user) {
        return (
            <button
                onClick={onLoginClick}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all ${isDark
                    ? 'bg-zinc-800 border-zinc-700 hover:border-zinc-600 text-zinc-200'
                    : 'bg-white border-zinc-300 hover:border-zinc-400 text-zinc-800'
                    }`}
            >
                <User size={16} className="text-zinc-500" />
                <span className="text-sm">登录</span>
            </button>
        );
    }

    return (
        <div ref={menuRef} className="relative">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all ${isDark
                    ? 'bg-zinc-800 border-zinc-700 hover:border-zinc-600 text-zinc-200'
                    : 'bg-white border-zinc-300 hover:border-zinc-400 text-zinc-800'
                    }`}
            >
                <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center text-xs font-medium text-white">
                    {user.display_name?.[0] || user.username?.[0] || 'U'}
                </div>
                <span className="text-sm font-medium max-w-[100px] truncate">
                    {user.display_name || user.username}
                </span>
                <ChevronDown size={14} className={`text-zinc-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </button>

            {isOpen && (
                <div
                    className={`absolute right-0 top-full mt-2 w-48 py-2 rounded-xl border shadow-xl z-[9999] ${isDark
                        ? 'bg-zinc-900 border-zinc-700 text-zinc-200'
                        : 'bg-white border-zinc-300 text-zinc-800'
                        }`}
                >
                    <div className="px-4 py-2 border-b border-zinc-700/50">
                        <p className="text-sm font-medium">{user.display_name || user.username}</p>
                        <p className="text-xs text-zinc-500">{user.email || ''}</p>
                    </div>
                    <button
                        onClick={() => {
                            onLogout();
                            setIsOpen(false);
                        }}
                        className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 transition-colors ${isDark ? 'hover:bg-zinc-800 text-red-400' : 'hover:bg-zinc-100 text-red-500'
                            }`}
                    >
                        <LogOut size={14} />
                        退出登录
                    </button>
                </div>
            )}
        </div>
    );
};

export const ProjectModal = ({ isOpen, onClose, onSelectProject, onCreateProject, onDeleteProject, currentProjectId, theme, getLocalServerUrl }) => {
    const [projects, setProjects] = useState([]);
    const [loading, setLoading] = useState(false);
    const [newProjectName, setNewProjectName] = useState('');
    const [showCreateForm, setShowCreateForm] = useState(false);
    const [createLoading, setCreateLoading] = useState(false);
    const isDark = theme === 'dark';
    const isSolarized = theme === 'solarized';

    useEffect(() => {
        if (isOpen) {
            loadProjects();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen]);

    const loadProjects = async () => {
        setLoading(true);
        try {
            const baseUrl = resolveLocalServerUrl(getLocalServerUrl);
            const token = localStorage.getItem('tapnow_auth_token');
            const res = await fetch(`${baseUrl}/projects`, {
                headers: token ? { Authorization: `Bearer ${token}` } : {}
            });
            if (res.ok) {
                const data = await res.json();
                if (data.success) {
                    setProjects(data.projects || []);
                }
            }
        } catch (e2) {
            console.error('Failed to load projects:', e2);
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = async (e) => {
        e.preventDefault();
        if (!newProjectName.trim()) return;

        setCreateLoading(true);
        try {
            const baseUrl = resolveLocalServerUrl(getLocalServerUrl);
            const token = localStorage.getItem('tapnow_auth_token');
            const res = await fetch(`${baseUrl}/projects`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: `Bearer ${token}` } : {})
                },
                body: JSON.stringify({ name: newProjectName.trim() })
            });

            if (res.ok) {
                const data = await res.json();
                if (data.success) {
                    onCreateProject(data.project);
                    setNewProjectName('');
                    setShowCreateForm(false);
                    onClose();
                }
            }
        } catch (e2) {
            console.error('Failed to create project:', e2);
        } finally {
            setCreateLoading(false);
        }
    };

    const handleDelete = async (projectId) => {
        if (!window.confirm('确定要删除这个项目吗？此操作不可撤销。')) return;

        try {
            const baseUrl = resolveLocalServerUrl(getLocalServerUrl);
            const token = localStorage.getItem('tapnow_auth_token');
            const res = await fetch(`${baseUrl}/projects/${projectId}`, {
                method: 'DELETE',
                headers: token ? { Authorization: `Bearer ${token}` } : {}
            });

            if (res.ok) {
                const data = await res.json();
                if (data.success) {
                    onDeleteProject(projectId);
                    setProjects(projects.filter((p) => p.id !== projectId));
                }
            }
        } catch (e2) {
            console.error('Failed to delete project:', e2);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div
                className={`w-full max-w-lg max-h-[80vh] flex flex-col rounded-2xl border shadow-2xl ${isDark
                    ? 'bg-zinc-900 border-zinc-700 text-zinc-200'
                    : isSolarized
                        ? 'bg-[#fdf6e3] border-[#d7cfb2] text-[#586e75]'
                        : 'bg-white border-zinc-300 text-zinc-800'
                    }`}
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between p-4 border-b border-zinc-700/50">
                    <h2 className="text-xl font-bold">项目管理</h2>
                    <button onClick={onClose} className="p-1 rounded hover:bg-zinc-700/50">
                        <X size={20} />
                    </button>
                </div>

                <div className="flex-1 overflow-auto p-4">
                    {!showCreateForm ? (
                        <button
                            onClick={() => setShowCreateForm(true)}
                            className={`w-full p-4 rounded-xl border-2 border-dashed mb-4 flex items-center justify-center gap-2 transition-all ${isDark
                                ? 'border-zinc-700 hover:border-blue-600 text-zinc-400 hover:text-blue-400'
                                : 'border-zinc-300 hover:border-blue-500 text-zinc-500 hover:text-blue-500'
                                }`}
                        >
                            <Plus size={20} />
                            <span className="font-medium">创建新项目</span>
                        </button>
                    ) : (
                        <form onSubmit={handleCreate} className="mb-4 p-4 rounded-xl border border-zinc-700/50 bg-zinc-800/30">
                            <input
                                type="text"
                                value={newProjectName}
                                onChange={(e) => setNewProjectName(e.target.value)}
                                className={`w-full px-3 py-2 rounded-lg border text-sm mb-3 ${isDark
                                    ? 'bg-zinc-800 border-zinc-700 text-zinc-200'
                                    : 'bg-white border-zinc-300 text-zinc-800'
                                    }`}
                                placeholder="项目名称"
                                autoFocus
                            />
                            <div className="flex gap-2">
                                <button
                                    type="button"
                                    onClick={() => setShowCreateForm(false)}
                                    className="flex-1 py-2 rounded-lg border border-zinc-600 text-sm hover:bg-zinc-800 transition-colors"
                                >
                                    取消
                                </button>
                                <button
                                    type="submit"
                                    disabled={createLoading || !newProjectName.trim()}
                                    className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm transition-colors disabled:opacity-50"
                                >
                                    {createLoading ? '创建中...' : '创建'}
                                </button>
                            </div>
                        </form>
                    )}

                    <div className="space-y-2">
                        <h3 className="text-sm font-medium text-zinc-500 mb-2">我的项目</h3>
                        {loading ? (
                            <div className="flex items-center justify-center py-8">
                                <Loader2 size={24} className="animate-spin text-zinc-500" />
                            </div>
                        ) : projects.length === 0 ? (
                            <div className="text-center py-8 text-zinc-500">
                                暂无项目，点击上方创建新项目
                            </div>
                        ) : (
                            projects.map((project) => (
                                <div
                                    key={project.id}
                                    className={`p-3 rounded-lg border flex items-center justify-between group transition-all ${currentProjectId === project.id
                                        ? isDark ? 'bg-blue-900/20 border-blue-800' : 'bg-blue-50 border-blue-300'
                                        : isDark ? 'bg-zinc-800/50 border-zinc-700 hover:border-zinc-600' : 'bg-zinc-50 border-zinc-200 hover:border-zinc-300'
                                        }`}
                                >
                                    <button
                                        onClick={() => {
                                            onSelectProject(project);
                                            onClose();
                                        }}
                                        className="flex-1 text-left"
                                    >
                                        <div className="font-medium">{project.name}</div>
                                        <div className="text-xs text-zinc-500">
                                            {(() => {
                                                const editorName = (project.updated_by_display_name || project.updated_by_username || '').trim();
                                                const savedAtText = project.updated_at
                                                    ? ` · 保存于 ${new Date(project.updated_at * 1000).toLocaleString('zh-CN')}`
                                                    : '';
                                                const editorText = project.updated_at
                                                    ? ` · 编辑者 ${editorName || '未知'}`
                                                    : '';
                                                return `创建于 ${new Date((project.created_at || 0) * 1000).toLocaleString('zh-CN')}${savedAtText}${editorText}`;
                                            })()}
                                        </div>
                                    </button>
                                    <button
                                        onClick={() => handleDelete(project.id)}
                                        className={`p-2 rounded opacity-0 group-hover:opacity-100 hover:bg-red-900/30 text-zinc-500 hover:text-red-400 transition-all ${isDark ? '' : 'hover:bg-red-50'}
                                            }`}
                                    >
                                        <Trash2 size={16} />
                                    </button>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

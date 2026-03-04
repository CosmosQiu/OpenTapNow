import React, { useState, useEffect } from 'react';
import { X, User, Lock, LogOut, Folder, Plus, Save, Trash2 } from 'lucide-react';

// 登录弹窗组件
export const LoginModal = ({ isOpen, onClose, onLogin, theme = 'dark' }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (isOpen) {
            setError('');
            setUsername('');
            setPassword('');
        }
    }, [isOpen]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const baseUrl = localStorage.getItem('tapnow_local_server_url') || 'http://127.0.0.1:9527';
            const res = await fetch(`${baseUrl}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });

            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.error || '登录失败');
            }

            const data = await res.json();
            if (data.token) {
                localStorage.setItem('tapnow_auth_token', data.token);
                localStorage.setItem('tapnow_user', JSON.stringify(data.user));
                onLogin(data.user);
                onClose();
            }
        } catch (err) {
            setError(err.message || '登录失败，请检查用户名和密码');
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    const isDark = theme === 'dark';

    return (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className={`rounded-xl shadow-2xl w-[400px] max-w-[90vw] overflow-hidden animate-in fade-in zoom-in-95 duration-200 border ${
                isDark ? 'bg-[#09090b] border-zinc-800' : 'bg-white border-zinc-200'
            }`}>
                <div className={`flex items-center justify-between px-5 py-4 border-b ${
                    isDark ? 'border-zinc-800' : 'border-zinc-200'
                }`}>
                    <h3 className={`text-lg font-semibold ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                        登录
                    </h3>
                    <button
                        onClick={onClose}
                        className={`p-1 rounded hover:bg-zinc-800/50 ${isDark ? 'text-zinc-400' : 'text-zinc-500'}`}
                    >
                        <X size={18} />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="p-5 space-y-4">
                    {error && (
                        <div className="px-3 py-2 rounded bg-red-900/30 border border-red-800 text-red-200 text-sm">
                            {error}
                        </div>
                    )}

                    <div className="space-y-2">
                        <label className={`text-sm ${isDark ? 'text-zinc-400' : 'text-zinc-600'}`}>
                            用户名
                        </label>
                        <div className="relative">
                            <User size={16} className={`absolute left-3 top-1/2 -translate-y-1/2 ${
                                isDark ? 'text-zinc-500' : 'text-zinc-400'
                            }`} />
                            <input
                                type="text"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                className={`w-full pl-10 pr-3 py-2 rounded border text-sm outline-none focus:ring-2 focus:ring-blue-500/50 ${
                                    isDark 
                                        ? 'bg-zinc-900 border-zinc-700 text-zinc-100 placeholder-zinc-600' 
                                        : 'bg-white border-zinc-300 text-zinc-900 placeholder-zinc-400'
                                }`}
                                placeholder="请输入用户名"
                                autoFocus
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <label className={`text-sm ${isDark ? 'text-zinc-400' : 'text-zinc-600'}`}>
                            密码
                        </label>
                        <div className="relative">
                            <Lock size={16} className={`absolute left-3 top-1/2 -translate-y-1/2 ${
                                isDark ? 'text-zinc-500' : 'text-zinc-400'
                            }`} />
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className={`w-full pl-10 pr-3 py-2 rounded border text-sm outline-none focus:ring-2 focus:ring-blue-500/50 ${
                                    isDark 
                                        ? 'bg-zinc-900 border-zinc-700 text-zinc-100 placeholder-zinc-600' 
                                        : 'bg-white border-zinc-300 text-zinc-900 placeholder-zinc-400'
                                }`}
                                placeholder="请输入密码"
                            />
                        </div>
                    </div>

                    <div className="pt-2">
                        <button
                            type="submit"
                            disabled={loading || !username || !password}
                            className={`w-full py-2.5 rounded font-medium transition-all ${
                                loading || !username || !password
                                    ? 'opacity-50 cursor-not-allowed'
                                    : 'hover:opacity-90'
                            } ${
                                isDark 
                                    ? 'bg-blue-600 text-white' 
                                    : 'bg-blue-500 text-white'
                            }`}
                        >
                            {loading ? '登录中...' : '登录'}
                        </button>
                    </div>

                    <p className={`text-xs text-center ${isDark ? 'text-zinc-500' : 'text-zinc-400'}`}>
                        默认账号: admin / admin123
                    </p>
                </form>
            </div>
        </div>
    );
};

// 项目管理弹窗
export const ProjectModal = ({ isOpen, onClose, onSelectProject, onCreateProject, onDeleteProject, currentProjectId, theme = 'dark' }) => {
    const [projects, setProjects] = useState([]);
    const [loading, setLoading] = useState(false);
    const [newProjectName, setNewProjectName] = useState('');
    const [showCreateForm, setShowCreateForm] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        if (isOpen) {
            loadProjects();
        }
    }, [isOpen]);

    const loadProjects = async () => {
        setLoading(true);
        try {
            const baseUrl = localStorage.getItem('tapnow_local_server_url') || 'http://127.0.0.1:9527';
            const token = localStorage.getItem('tapnow_auth_token');
            
            const res = await fetch(`${baseUrl}/projects`, {
                headers: token ? { 'Authorization': `Bearer ${token}` } : {}
            });
            
            if (res.ok) {
                const data = await res.json();
                setProjects(data.projects || []);
            }
        } catch (err) {
            console.error('加载项目失败:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = async (e) => {
        e.preventDefault();
        if (!newProjectName.trim()) return;

        setLoading(true);
        try {
            const baseUrl = localStorage.getItem('tapnow_local_server_url') || 'http://127.0.0.1:9527';
            const token = localStorage.getItem('tapnow_auth_token');
            
            const res = await fetch(`${baseUrl}/projects`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                },
                body: JSON.stringify({ name: newProjectName.trim() })
            });

            if (res.ok) {
                const data = await res.json();
                setNewProjectName('');
                setShowCreateForm(false);
                await loadProjects();
                if (onCreateProject) onCreateProject(data.project);
            } else {
                const err = await res.json();
                setError(err.error || '创建失败');
            }
        } catch (err) {
            setError('创建项目失败');
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (projectId) => {
        if (!confirm('确定要删除这个项目吗？')) return;

        try {
            const baseUrl = localStorage.getItem('tapnow_local_server_url') || 'http://127.0.0.1:9527';
            const token = localStorage.getItem('tapnow_auth_token');
            
            const res = await fetch(`${baseUrl}/projects/${projectId}`, {
                method: 'DELETE',
                headers: token ? { 'Authorization': `Bearer ${token}` } : {}
            });

            if (res.ok) {
                await loadProjects();
                if (onDeleteProject) onDeleteProject(projectId);
            }
        } catch (err) {
            console.error('删除项目失败:', err);
        }
    };

    const handleSelect = (project) => {
        if (onSelectProject) onSelectProject(project);
        onClose();
    };

    if (!isOpen) return null;

    const isDark = theme === 'dark';

    return (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className={`rounded-xl shadow-2xl w-[500px] max-w-[90vw] max-h-[80vh] overflow-hidden animate-in fade-in zoom-in-95 duration-200 border flex flex-col ${
                isDark ? 'bg-[#09090b] border-zinc-800' : 'bg-white border-zinc-200'
            }`}>
                <div className={`flex items-center justify-between px-5 py-4 border-b ${
                    isDark ? 'border-zinc-800' : 'border-zinc-200'
                }`}>
                    <h3 className={`text-lg font-semibold ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                        项目管理
                    </h3>
                    <button
                        onClick={onClose}
                        className={`p-1 rounded hover:bg-zinc-800/50 ${isDark ? 'text-zinc-400' : 'text-zinc-500'}`}
                    >
                        <X size={18} />
                    </button>
                </div>

                <div className="p-5 flex-1 overflow-hidden flex flex-col">
                    {error && (
                        <div className="mb-4 px-3 py-2 rounded bg-red-900/30 border border-red-800 text-red-200 text-sm">
                            {error}
                        </div>
                    )}

                    {!showCreateForm ? (
                        <button
                            onClick={() => setShowCreateForm(true)}
                            className={`mb-4 flex items-center justify-center gap-2 py-2.5 rounded border-2 border-dashed transition-all ${
                                isDark 
                                    ? 'border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300' 
                                    : 'border-zinc-300 text-zinc-500 hover:border-zinc-400 hover:text-zinc-600'
                            }`}
                        >
                            <Plus size={18} />
                            新建项目
                        </button>
                    ) : (
                        <form onSubmit={handleCreate} className="mb-4 flex gap-2">
                            <input
                                type="text"
                                value={newProjectName}
                                onChange={(e) => setNewProjectName(e.target.value)}
                                placeholder="输入项目名称"
                                className={`flex-1 px-3 py-2 rounded border text-sm outline-none focus:ring-2 focus:ring-blue-500/50 ${
                                    isDark 
                                        ? 'bg-zinc-900 border-zinc-700 text-zinc-100' 
                                        : 'bg-white border-zinc-300 text-zinc-900'
                                }`}
                                autoFocus
                            />
                            <button
                                type="submit"
                                disabled={loading || !newProjectName.trim()}
                                className="px-4 py-2 bg-blue-600 text-white rounded text-sm font-medium disabled:opacity-50"
                            >
                                创建
                            </button>
                            <button
                                type="button"
                                onClick={() => setShowCreateForm(false)}
                                className={`px-4 py-2 rounded text-sm border ${
                                    isDark 
                                        ? 'border-zinc-700 text-zinc-400 hover:bg-zinc-800' 
                                        : 'border-zinc-300 text-zinc-600 hover:bg-zinc-100'
                                }`}
                            >
                                取消
                            </button>
                        </form>
                    )}

                    <div className="flex-1 overflow-y-auto space-y-2">
                        {loading && projects.length === 0 ? (
                            <div className={`text-center py-8 ${isDark ? 'text-zinc-500' : 'text-zinc-400'}`}>
                                加载中...
                            </div>
                        ) : projects.length === 0 ? (
                            <div className={`text-center py-8 ${isDark ? 'text-zinc-500' : 'text-zinc-400'}`}>
                                暂无项目，点击上方创建新项目
                            </div>
                        ) : (
                            projects.map(project => (
                                <div
                                    key={project.id}
                                    className={`group flex items-center justify-between p-3 rounded border cursor-pointer transition-all ${
                                        currentProjectId === project.id
                                            ? (isDark ? 'bg-blue-900/20 border-blue-800' : 'bg-blue-50 border-blue-200')
                                            : (isDark ? 'bg-zinc-900/50 border-zinc-800 hover:border-zinc-700' : 'bg-zinc-50 border-zinc-200 hover:border-zinc-300')
                                    }`}
                                >
                                    <div
                                        className="flex items-center gap-3 flex-1"
                                        onClick={() => handleSelect(project)}
                                    >
                                        <Folder size={18} className={
                                            currentProjectId === project.id
                                                ? (isDark ? 'text-blue-400' : 'text-blue-500')
                                                : (isDark ? 'text-zinc-500' : 'text-zinc-400')
                                        } />
                                        <div>
                                            <div className={`font-medium ${
                                                currentProjectId === project.id
                                                    ? (isDark ? 'text-zinc-100' : 'text-zinc-900')
                                                    : (isDark ? 'text-zinc-300' : 'text-zinc-700')
                                            }`}>
                                                {project.name}
                                            </div>
                                            <div className={`text-xs ${isDark ? 'text-zinc-500' : 'text-zinc-400'}`}>
                                                更新于 {new Date(project.updated_at * 1000).toLocaleString()}
                                            </div>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => handleDelete(project.id)}
                                        className={`p-2 rounded opacity-0 group-hover:opacity-100 transition-all ${
                                            isDark ? 'hover:bg-red-900/30 text-zinc-500 hover:text-red-400' : 'hover:bg-red-50 text-zinc-400 hover:text-red-500'
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

// 用户菜单组件
export const UserMenu = ({ user, onLoginClick, onLogout, theme = 'dark' }) => {
    const [isOpen, setIsOpen] = useState(false);
    const menuRef = React.useRef(null);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (menuRef.current && !menuRef.current.contains(event.target)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleLogout = () => {
        localStorage.removeItem('tapnow_auth_token');
        localStorage.removeItem('tapnow_user');
        if (onLogout) onLogout();
        setIsOpen(false);
    };

    const isDark = theme === 'dark';

    if (!user) {
        return (
            <button
                onClick={onLoginClick}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                    isDark 
                        ? 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700 border border-zinc-700' 
                        : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200 border border-zinc-300'
                }`}
            >
                <User size={16} />
                登录
            </button>
        );
    }

    return (
        <div className="relative" ref={menuRef}>
            <button
                onClick={() => setIsOpen(!isOpen)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                    isDark 
                        ? 'bg-blue-900/30 text-blue-300 hover:bg-blue-900/50 border border-blue-800' 
                        : 'bg-blue-50 text-blue-600 hover:bg-blue-100 border border-blue-200'
                }`}
            >
                <User size={16} />
                {user.display_name || user.username}
            </button>

            {isOpen && (
                <div className={`absolute right-0 top-full mt-2 w-40 rounded-lg border shadow-xl py-1 z-[9999] ${
                    isDark ? 'bg-zinc-900 border-zinc-800' : 'bg-white border-zinc-200'
                }`}>
                    <button
                        onClick={handleLogout}
                        className={`w-full flex items-center gap-2 px-4 py-2 text-sm transition-all ${
                            isDark 
                                ? 'text-zinc-300 hover:bg-zinc-800' 
                                : 'text-zinc-700 hover:bg-zinc-100'
                        }`}
                    >
                        <LogOut size={16} />
                        退出登录
                    </button>
                </div>
            )}
        </div>
    );
};

// 项目选择器组件
export const ProjectSelector = ({ project, onClick, theme = 'dark' }) => {
    const isDark = theme === 'dark';

    return (
        <button
            onClick={onClick}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-all max-w-[200px] truncate ${
                isDark 
                    ? 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700 border border-zinc-700' 
                    : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200 border border-zinc-300'
            }`}
            title={project?.name || '选择项目'}
        >
            <Folder size={16} />
            <span className="truncate">{project?.name || '选择项目'}</span>
        </button>
    );
};

export default { LoginModal, ProjectModal, UserMenu, ProjectSelector };

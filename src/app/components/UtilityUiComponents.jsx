import React, { useState } from 'react';

export const TagListEditor = ({
    label,
    values,
    onChange,
    placeholder,
    addLabel = '+',
    formatItem = (value) => value,
    disabled = false,
    inputDisabled = false,
    theme = 'dark',
    allowAll = false,
    allowAllLabel = '',
    onToggleAll = null,
    normalizeItem = (value) => value,
    maxItems = Infinity,
    allLabelPosition = 'right',
    headerLeft = null,
    headerRight = null
}) => {
    const [inputValue, setInputValue] = useState('');
    const list = Array.isArray(values) ? values : [];
    const listDisabled = disabled || inputDisabled;
    const maxCount = Number.isFinite(maxItems) ? maxItems : Infinity;
    const isMaxed = list.length >= maxCount;

    const addValues = () => {
        if (listDisabled) return;
        if (isMaxed) return;
        const raw = inputValue.trim();
        if (!raw) return;
        const parts = raw.split(',').map(part => part.trim()).filter(Boolean);
        if (parts.length === 0) return;
        const next = [...list];
        parts.forEach((part) => {
            const normalized = normalizeItem(part);
            if (next.length >= maxCount) return;
            if (normalized && !next.includes(normalized)) {
                next.push(normalized);
            }
        });
        onChange(next);
        setInputValue('');
    };

    const removeValue = (value) => {
        if (listDisabled) return;
        onChange(list.filter(item => item !== value));
    };

    const allLabelNode = allowAllLabel ? (
        <label className={`flex items-center gap-1 text-[9px] ${theme === 'dark' ? 'text-zinc-500' : 'text-zinc-600'}`}>
            <input
                type="checkbox"
                checked={!!allowAll}
                onChange={(e) => onToggleAll && onToggleAll(e.target.checked)}
                disabled={disabled}
            />
            <span>{allowAllLabel}</span>
        </label>
    ) : null;
    const hasRightHeader = (allLabelPosition !== 'left' && !!allLabelNode) || !!headerRight;
    return (
        <div className="space-y-1">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <label className={`text-[9px] font-medium uppercase tracking-wider ${theme === 'dark' ? 'text-zinc-500' : 'text-zinc-600'}`}>{label}</label>
                    {Number.isFinite(maxCount) && maxCount !== Infinity && (
                        <span className={`text-[9px] ${theme === 'dark' ? 'text-zinc-600' : 'text-zinc-500'}`}>({list.length}/{maxCount})</span>
                    )}
                    {headerLeft}
                    {allLabelPosition === 'left' && allLabelNode}
                </div>
                {hasRightHeader && (
                    <div className="flex items-center gap-2">
                        {allLabelPosition !== 'left' && allLabelNode}
                        {headerRight}
                    </div>
                )}
            </div>
            <div className="flex flex-wrap gap-1 min-h-[18px]">
                {list.length > 0 ? list.map((item) => (
                    <span
                        key={item}
                        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] ${theme === 'dark'
                            ? 'bg-zinc-800 text-zinc-300'
                            : 'bg-zinc-100 text-zinc-600'
                            }`}
                    >
                        {formatItem(item)}
                        {!listDisabled && (
                            <button
                                onClick={() => removeValue(item)}
                                className={`${theme === 'dark' ? 'text-zinc-500 hover:text-red-400' : 'text-zinc-400 hover:text-red-500'}`}
                            >
                                x
                            </button>
                        )}
                    </span>
                )) : (
                    <span className={`text-[9px] ${theme === 'dark' ? 'text-zinc-600' : 'text-zinc-400'}`}>未设置</span>
                )}
            </div>
            <div className="flex items-center gap-1">
                <input
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                            e.preventDefault();
                            addValues();
                        }
                    }}
                    placeholder={placeholder}
                    disabled={listDisabled}
                    className={`flex-1 rounded px-2 py-1 text-[10px] outline-none border ${theme === 'dark'
                        ? 'bg-zinc-900 border-zinc-800 text-zinc-300'
                        : 'bg-white border-zinc-300 text-zinc-900'
                        }`}
                />
                <button
                    onClick={addValues}
                    disabled={listDisabled || !inputValue.trim() || isMaxed}
                    className={`px-2 py-1 rounded text-[10px] ${listDisabled || !inputValue.trim() || isMaxed
                        ? theme === 'dark'
                            ? 'bg-zinc-800 text-zinc-600 cursor-not-allowed'
                            : 'bg-zinc-100 text-zinc-400 cursor-not-allowed'
                        : theme === 'dark'
                            ? 'bg-zinc-700 text-zinc-200 hover:bg-zinc-600'
                            : 'bg-zinc-200 text-zinc-700 hover:bg-zinc-300'
                        }`}
                >
                    {addLabel}
                </button>
            </div>
        </div>
    );
};

export const ArtisticProgress = ({ visible, progress, status, type }) => {
    if (!visible) return null;

    return (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40 backdrop-blur-[2px] animate-in fade-in duration-300 pointer-events-none select-none">
            <div className="relative bg-[#09090b]/90 border border-white/10 rounded-2xl p-8 shadow-2xl flex flex-col items-center min-w-[300px] backdrop-blur-xl">
                <div className="absolute -top-10 left-1/2 -translate-x-1/2 w-20 h-20 bg-blue-500/20 blur-[50px] rounded-full pointer-events-none" />

                <div className="flex flex-col items-center gap-1 mb-6 z-10">
                    <span className="font-mono text-[10px] tracking-[0.3em] uppercase text-zinc-500">
                        {type === 'import' ? 'DATA INGESTION' : 'SYSTEM ARCHIVING'}
                    </span>
                    <div className="text-4xl font-bold text-zinc-200 tracking-tighter font-sans">
                        {progress.toFixed(0)}<span className="text-sm text-zinc-500 ml-1">%</span>
                    </div>
                </div>

                <div className="relative w-full h-[2px] bg-zinc-800 rounded-full overflow-hidden mb-4">
                    <div
                        className="absolute top-0 left-0 h-full bg-white shadow-[0_0_10px_rgba(255,255,255,0.5)] transition-all duration-100 ease-linear"
                        style={{ width: `${progress}%` }}
                    />
                </div>

                <span className="text-[10px] font-mono text-zinc-400 tracking-widest uppercase animate-pulse">
                    {status}
                </span>
            </div>
        </div>
    );
};

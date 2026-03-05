import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, Eraser, Undo2 } from 'lucide-react';

export const createMediaCoreComponents = (deps) => {
    const {
        LocalImageManager,
        getAssetBundleFallbackById,
        normalizeDataUrl,
        dataUrlToBlob,
        MaskVisualFeedback,
        getImageDimensions,
        t
    } = deps;

    const LazyBase64Image = ({ src, className, alt, onError, onLoad, ...props }) => {
        const [blobUrl, setBlobUrl] = useState(null);
        const [error, setError] = useState(false);
        const [loading, setLoading] = useState(false);
        const blobUrlRef = useRef(null);

        useEffect(() => {
            let active = true;
            if (blobUrlRef.current && blobUrlRef.current.startsWith('blob:')) {
                URL.revokeObjectURL(blobUrlRef.current);
            }
            blobUrlRef.current = null;
            setError(false);
            setBlobUrl(null);
            if (!src || src.startsWith('blob:') || src.startsWith('http://') || src.startsWith('https://')) {
                if (active) {
                    setBlobUrl(src);
                    setLoading(false);
                }
                return () => { active = false; };
            }

            if (LocalImageManager.isImageId(src)) {
                setLoading(true);
                const resolveFromIDB = async () => {
                    try {
                        const url = await LocalImageManager.getImage(src);
                        if (!active) return;
                        if (url) {
                            blobUrlRef.current = url;
                            setBlobUrl(url);
                        } else {
                            const fallback = getAssetBundleFallbackById(src);
                            if (fallback) {
                                blobUrlRef.current = fallback;
                                setBlobUrl(fallback);
                            } else {
                                console.warn(`[LazyBase64Image] Image not found in IDB: ${src}`);
                                setError(true);
                            }
                        }
                    } catch (err) {
                        if (!active) return;
                        console.error('[LazyBase64Image] IDB resolve failed:', err);
                        setError(true);
                    }
                    if (active) setLoading(false);
                };
                resolveFromIDB();
                return () => { active = false; };
            }

            if (src.startsWith('data:')) {
                const normalized = normalizeDataUrl(src);
                const isFileProtocol = typeof window !== 'undefined' && window.location?.protocol === 'file:';
                if (isFileProtocol) {
                    if (active) {
                        blobUrlRef.current = normalized;
                        setBlobUrl(normalized);
                        setLoading(false);
                    }
                    return () => { active = false; };
                }
                const convertToBlobUrl = async () => {
                    try {
                        const blob = dataUrlToBlob(normalized);
                        if (!active) return;
                        if (!blob) {
                            setError(true);
                            setBlobUrl(null);
                            return;
                        }
                        const url = URL.createObjectURL(blob);
                        blobUrlRef.current = url;
                        setBlobUrl(url);
                    } catch (err) {
                        if (!active) return;
                        console.warn('Base64转Blob失败', err);
                        setError(true);
                        setBlobUrl(null);
                    }
                };
                convertToBlobUrl();
            } else {
                setBlobUrl(src);
            }

            return () => {
                active = false;
                if (blobUrlRef.current && blobUrlRef.current.startsWith('blob:')) {
                    URL.revokeObjectURL(blobUrlRef.current);
                    blobUrlRef.current = null;
                }
            };
        }, [src]);

        if (loading) return null;
        if (error && !blobUrl) return null;
        if (!blobUrl || LocalImageManager.isImageId(blobUrl)) return null;

        return (
            <img
                src={blobUrl}
                className={className}
                alt={alt}
                onError={onError}
                onLoad={onLoad}
                {...props}
            />
        );
    };

    const ResolvedVideo = ({ src, className, onError, onLoadedMetadata, ...props }) => {
        const [resolvedSrc, setResolvedSrc] = useState('');
        useEffect(() => {
            let active = true;
            setResolvedSrc('');
            if (!src) {
                return () => { active = false; };
            }
            if (LocalImageManager.isImageId(src)) {
                (async () => {
                    const dataUrl = await LocalImageManager.getImage(src);
                    if (!active) return;
                    if (dataUrl) {
                        setResolvedSrc(dataUrl);
                    } else {
                        const fallback = getAssetBundleFallbackById(src);
                        setResolvedSrc(fallback || '');
                    }
                })();
                return () => { active = false; };
            }
            setResolvedSrc(src);
            return () => { active = false; };
        }, [src]);

        if (!resolvedSrc) return null;

        return (
            <video
                src={resolvedSrc}
                className={className}
                onError={onError}
                onLoadedMetadata={onLoadedMetadata}
                {...props}
            />
        );
    };

    const MaskEditor = ({ nodeId, imageUrl, imageDimensions, isActive, onClose, onSave, theme, maskContent, onUpdateNode }) => {
        const canvasRef = useRef(null);
        const ctxRef = useRef(null);
        const lastPointRef = useRef(null);
        const [brushSize, setBrushSize] = useState(30);
        const [isDrawing, setIsDrawing] = useState(false);
        const [history, setHistory] = useState([]);
        const [historyIndex, setHistoryIndex] = useState(-1);
        const maxHistory = 10;
        const [resolvedDimensions, setResolvedDimensions] = useState(imageDimensions);

        useEffect(() => {
            if (imageDimensions?.w && imageDimensions?.h) {
                setResolvedDimensions(imageDimensions);
            }
        }, [imageDimensions]);

        useEffect(() => {
            if (!isActive || !imageUrl) return;
            if (imageDimensions?.w && imageDimensions?.h) return;
            let cancelled = false;
            getImageDimensions(imageUrl)
                .then((dims) => {
                    if (cancelled) return;
                    if (dims?.w && dims?.h) {
                        setResolvedDimensions(dims);
                        if (onUpdateNode) onUpdateNode(nodeId, { dimensions: dims });
                    }
                })
                .catch(() => { });
            return () => { cancelled = true; };
        }, [isActive, imageUrl, imageDimensions, nodeId, onUpdateNode]);

        useEffect(() => {
            if (!isActive || !canvasRef.current || !resolvedDimensions) return;
            const canvas = canvasRef.current;
            const ctx = canvas.getContext('2d');
            ctxRef.current = ctx;
            canvas.width = resolvedDimensions.w;
            canvas.height = resolvedDimensions.h;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            if (maskContent) {
                const img = new Image();
                img.onload = () => {
                    ctx.drawImage(img, 0, 0);
                    saveToHistory();
                };
                img.src = maskContent;
            } else {
                saveToHistory();
            }
        }, [isActive, resolvedDimensions, nodeId, maskContent]);

        const saveToHistory = () => {
            if (!canvasRef.current || !ctxRef.current) return;
            const canvas = canvasRef.current;
            const ctx = ctxRef.current;
            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const newHistory = history.slice(0, historyIndex + 1);
            newHistory.push(imageData);
            if (newHistory.length > maxHistory) {
                newHistory.shift();
            }
            setHistory(newHistory);
            setHistoryIndex(newHistory.length - 1);
        };

        const getCanvasCoordinates = (e) => {
            if (!canvasRef.current) return null;
            const canvas = canvasRef.current;
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            return { x: Math.round(x * scaleX), y: Math.round(y * scaleY) };
        };

        const draw = (e) => {
            if (!isDrawing || !canvasRef.current || !ctxRef.current) return;
            const coords = getCanvasCoordinates(e);
            if (!coords) return;
            const ctx = ctxRef.current;
            ctx.globalCompositeOperation = 'source-over';
            ctx.strokeStyle = '#FFFFFF';
            ctx.fillStyle = '#FFFFFF';
            ctx.lineWidth = brushSize;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            if (lastPointRef.current) {
                ctx.beginPath();
                ctx.moveTo(lastPointRef.current.x, lastPointRef.current.y);
                ctx.lineTo(coords.x, coords.y);
                ctx.stroke();
            } else {
                ctx.beginPath();
                ctx.arc(coords.x, coords.y, brushSize / 2, 0, Math.PI * 2);
                ctx.fill();
            }
            lastPointRef.current = coords;
        };

        const handleMouseDown = (e) => {
            if (e.button !== 0) return;
            e.preventDefault();
            e.stopPropagation();
            lastPointRef.current = null;
            setIsDrawing(true);
            saveToHistory();
            draw(e);
        };

        const handleMouseMove = (e) => {
            if (!isDrawing) return;
            e.preventDefault();
            e.stopPropagation();
            draw(e);
        };

        const handleMouseUp = (e) => {
            if (!isDrawing) return;
            e.preventDefault();
            e.stopPropagation();
            setIsDrawing(false);
            lastPointRef.current = null;
            saveToHistory();
        };

        const handleUndo = () => {
            if (historyIndex <= 0 || !canvasRef.current || !ctxRef.current) return;
            const newIndex = historyIndex - 1;
            setHistoryIndex(newIndex);
            const ctx = ctxRef.current;
            ctx.putImageData(history[newIndex], 0, 0);
        };

        const handleClear = () => {
            if (!canvasRef.current || !ctxRef.current) return;
            const ctx = ctxRef.current;
            ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
            saveToHistory();
        };

        const handleSave = () => {
            if (!canvasRef.current) return;
            const canvas = canvasRef.current;
            const maskDataUrl = canvas.toDataURL('image/png');
            if (onUpdateNode) {
                onUpdateNode(nodeId, { maskContent: maskDataUrl, isMasking: false });
            }
            if (onSave) onSave(maskDataUrl);
            if (onClose) onClose();
        };

        useEffect(() => {
            if (!isActive) return;
            const handleKeyDown = (e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
                    e.preventDefault();
                    handleUndo();
                }
            };
            window.addEventListener('keydown', handleKeyDown);
            return () => window.removeEventListener('keydown', handleKeyDown);
        }, [isActive, historyIndex, history]);

        if (!isActive || !imageUrl || !resolvedDimensions) return null;

        return (
            <>
                <div className="absolute inset-0 z-50 pointer-events-auto" style={{ mixBlendMode: 'normal' }}>
                    <canvas
                        ref={canvasRef}
                        className="absolute inset-0 w-full h-full"
                        style={{ opacity: 0.5, mixBlendMode: 'multiply', cursor: 'crosshair', pointerEvents: 'auto', imageRendering: 'auto' }}
                        onMouseDown={handleMouseDown}
                        onMouseMove={handleMouseMove}
                        onMouseUp={handleMouseUp}
                        onMouseLeave={handleMouseUp}
                    />
                    <MaskVisualFeedback canvasRef={canvasRef} isDrawing={isDrawing} />
                </div>

                {createPortal(
                    <div
                        className={`fixed bottom-4 left-1/2 -translate-x-1/2 flex flex-row items-center gap-4 p-2 rounded-full border backdrop-blur-md shadow-xl z-[9999] ${theme === 'dark'
                            ? 'bg-zinc-900/90 border-zinc-700 text-zinc-200'
                            : 'bg-white/90 border-zinc-300 text-zinc-800'
                            }`}
                        onMouseDown={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] font-medium whitespace-nowrap">笔刷</span>
                            <input
                                type="range"
                                min="10"
                                max="150"
                                value={brushSize}
                                onChange={(e) => setBrushSize(Number(e.target.value))}
                                className="w-20"
                                onMouseDown={(e) => e.stopPropagation()}
                            />
                            <span className="text-[10px] w-8 text-right whitespace-nowrap">{brushSize}px</span>
                        </div>

                        <div className="flex items-center gap-1">
                            <button
                                onClick={handleUndo}
                                disabled={historyIndex <= 0}
                                className={`p-1.5 rounded-full transition-colors ${theme === 'dark'
                                    ? 'hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed'
                                    : 'hover:bg-zinc-100 disabled:opacity-50 disabled:cursor-not-allowed'
                                    }`}
                                title={t('撤销 (Ctrl+Z)')}
                            >
                                <Undo2 size={14} />
                            </button>
                            <button
                                onClick={handleClear}
                                className={`p-1.5 rounded-full transition-colors ${theme === 'dark' ? 'hover:bg-zinc-800' : 'hover:bg-zinc-100'}`}
                                title={t('清空')}
                            >
                                <Eraser size={14} />
                            </button>
                            <button
                                onClick={handleSave}
                                className="p-1.5 rounded-full bg-blue-600 hover:bg-blue-500 text-white transition-colors"
                                title={t('保存/完成')}
                            >
                                <Check size={14} />
                            </button>
                        </div>
                    </div>,
                    document.body
                )}
            </>
        );
    };

    return {
        LazyBase64Image,
        ResolvedVideo,
        MaskEditor
    };
};

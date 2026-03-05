import React, { memo, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Loader2, RefreshCw, Trash2 } from 'lucide-react';

export const createHistoryItemComponents = (deps) => {
    const {
        t,
        truncateByBytes,
        isCompletedLikeStatus,
        IMAGE_BATCH_MODE_STANDARD_BATCH,
        IMAGE_BATCH_MODE_PARALLEL_AGGREGATE,
        LazyBase64Image,
        ResolvedVideo
    } = deps;

    const HistoryMjImageCell = memo(({
        item,
        idx,
        imgUrl,
        displayImgUrl,
        theme,
        canDrag,
        lightboxItem,
        onImageClick,
        onImageContextMenu,
        onCacheMissing,
        handleDragStart,
        language
    }) => {
        const [isLoaded, setIsLoaded] = useState(false);
        const [loadFailed, setLoadFailed] = useState(false);

        useEffect(() => {
            setIsLoaded(false);
            setLoadFailed(false);
        }, [displayImgUrl]);

        const isActive = item.selectedMjImageIndex === idx && lightboxItem && lightboxItem.id === item.id;
        const placeholderClass = theme === 'dark' ? 'text-zinc-500' : 'text-[#616161]';

        return (
            <div
                onClick={(e) => onImageClick && onImageClick(e, item, imgUrl, idx)}
                onContextMenu={(e) => onImageContextMenu && onImageContextMenu(e, item, imgUrl, idx)}
                onDragStart={(e) => {
                    if (!canDrag) return;
                    e.stopPropagation();
                    handleDragStart(e, imgUrl);
                }}
                draggable={canDrag}
                className={`relative w-full h-full cursor-pointer border-2 transition-all overflow-hidden ${isActive
                    ? 'border-blue-500 scale-95'
                    : 'border-transparent hover:border-blue-500/50'
                    }`}
            >
                <LazyBase64Image
                    src={displayImgUrl}
                    loading="lazy"
                    className="w-full h-full object-contain"
                    alt=""
                    onLoad={() => {
                        setIsLoaded(true);
                        setLoadFailed(false);
                    }}
                    onError={(e) => {
                        setIsLoaded(false);
                        setLoadFailed(true);
                        console.error(`图片 ${idx + 1} 加载失败`);
                        onCacheMissing && onCacheMissing(item.id, displayImgUrl);
                        e.target.style.display = 'none';
                    }}
                />
                {!isLoaded && (
                    <div
                        className={`absolute inset-0 flex items-center justify-center text-[12px] ${loadFailed ? 'text-red-400' : placeholderClass} pointer-events-none select-none`}
                        style={{ fontFamily: '"Microsoft YaHei","微软雅黑","KaiTi","楷体",serif' }}
                    >
                        {loadFailed ? t('加载失败') : `${t('图片')}${idx + 1}`}
                    </div>
                )}
                {isActive && (
                    <div className="absolute top-1 right-1 w-3 h-3 bg-blue-500 rounded-full flex items-center justify-center z-10">
                        <svg className="w-2 h-2 text-white" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                    </div>
                )}
            </div>
        );
    });

    const HistoryItem = memo(({
        item,
        theme,
        lightboxItem,
        onDelete,
        onClick,
        onContextMenu,
        onImageClick,
        onImageContextMenu,
        onRefresh,
        onRebuildThumbnail,
        performanceMode,
        localServerUrl,
        localCacheActive,
        onCacheMissing,
        getHistoryMeta,
        isSelected,
        onSelect,
        providers,
        defaultProviders,
        historyLocalCacheMap,
        resolveHistoryUrl,
        isLocalCacheUrlAvailable,
        language
    }) => {
        const multiImages = Array.isArray(item.mjImages) && item.mjImages.length > 1
            ? item.mjImages
            : (Array.isArray(item.output_images) && item.output_images.length > 1 ? item.output_images : null);
        const primaryUrl = item.url || item.originalUrl || item.mjOriginalUrl || (multiImages && multiImages.length > 0 ? multiImages[0] : null);
        const mappedCacheUrl = localCacheActive && primaryUrl
            ? (historyLocalCacheMap && historyLocalCacheMap.has(primaryUrl)
                ? historyLocalCacheMap.get(primaryUrl)
                : (item.localCacheMap ? item.localCacheMap[primaryUrl] : null))
            : null;
        const localCacheFallback = mappedCacheUrl || item.localCacheUrl || (item.localCacheMap ? Object.values(item.localCacheMap)[0] : null);
        const hasLocalCache = !!(localCacheActive && localCacheFallback && (!isLocalCacheUrlAvailable || isLocalCacheUrlAvailable(localCacheFallback)));
        const thumbnailUrl = item.thumbnailUrl || null;
        const canDrag = isCompletedLikeStatus(item.status) && (item.type === 'image' || (multiImages && multiImages.length > 0));
        const historyMeta = getHistoryMeta ? getHistoryMeta(item) : null;
        const resolvedModelLabel = historyMeta?.modelLabel;
        const rawModelName = (() => {
            if (resolvedModelLabel) return resolvedModelLabel;
            const fallback = item.apiConfig?.modelId || item.apiConfig?.model || item.model || item.modelName || '未知模型';
            if (item.modelName && item.provider && item.modelName.toLowerCase() === item.provider.toLowerCase()) return fallback;
            return item.modelName || fallback;
        })();
        const displayModelName = truncateByBytes(rawModelName, 15);
        const providerTitle = item.provider || item.apiConfig?.provider || '';
        const modelTooltip = providerTitle ? `${providerTitle} / ${rawModelName}` : rawModelName;
        const getDisplayUrl = (originalUrl) => {
            if (hasLocalCache) return localCacheFallback;
            if (performanceMode !== 'off' && thumbnailUrl) return thumbnailUrl;
            return originalUrl;
        };
        const getResolvedDisplayUrl = (originalUrl) => {
            const raw = getDisplayUrl(originalUrl);
            if (resolveHistoryUrl) return resolveHistoryUrl(item, raw);
            return raw;
        };
        const [videoSrc, setVideoSrc] = useState(null);
        const resolveItemUrl = (specificUrl = null) => {
            if (resolveHistoryUrl) return resolveHistoryUrl(item, specificUrl);
            if (specificUrl) {
                if (localCacheActive && item.localCacheMap && item.localCacheMap[specificUrl]) {
                    return item.localCacheMap[specificUrl];
                }
                return specificUrl;
            }
            return item.localCacheUrl || (item.localCacheMap ? Object.values(item.localCacheMap)[0] : '') || item.originalUrl || item.mjOriginalUrl || item.url || '';
        };
        const getDragUrl = (specificUrl = null) => {
            if (specificUrl) return resolveItemUrl(specificUrl);
            if (multiImages && multiImages.length > 0) {
                const index = item.selectedMjImageIndex ?? 0;
                const selected = multiImages[index] || multiImages[0];
                if (selected) return resolveItemUrl(selected);
            }
            return resolveItemUrl();
        };
        const getSelectedDragRawUrl = (specificUrl = null) => {
            if (specificUrl) return specificUrl;
            if (multiImages && multiImages.length > 0) {
                const rawIndex = Number.isInteger(item.selectedMjImageIndex) ? item.selectedMjImageIndex : 0;
                const clampedIndex = Math.max(0, Math.min(rawIndex, multiImages.length - 1));
                return multiImages[clampedIndex] || multiImages[0] || '';
            }
            return item.url || item.originalUrl || item.mjOriginalUrl || '';
        };
        const handleDragStart = (e, specificUrl = null) => {
            const selectedRawUrl = getSelectedDragRawUrl(specificUrl);
            const dragUrl = getDragUrl(selectedRawUrl || specificUrl);
            if (!dragUrl) return;
            const selectedIndex = (() => {
                if (!multiImages || multiImages.length === 0) return 0;
                if (selectedRawUrl) {
                    const idx = multiImages.indexOf(selectedRawUrl);
                    if (idx >= 0) return idx;
                }
                const rawIndex = Number.isInteger(item.selectedMjImageIndex) ? item.selectedMjImageIndex : 0;
                return Math.max(0, Math.min(rawIndex, multiImages.length - 1));
            })();
            const payload = {
                source: 'history',
                itemId: item.id,
                type: item.type || 'image',
                url: selectedRawUrl || dragUrl,
                originalUrl: item.originalUrl || item.mjOriginalUrl || item.url || dragUrl,
                mjOriginalUrl: item.mjOriginalUrl || item.originalUrl || item.url || dragUrl,
                mjImages: multiImages ? multiImages.slice(0, 12) : null,
                selectedIndex
            };
            e.dataTransfer.effectAllowed = 'copy';
            e.dataTransfer.setData('application/x-tapnow-history', JSON.stringify(payload));
            e.dataTransfer.setData('text/uri-list', dragUrl);
            e.dataTransfer.setData('text/plain', dragUrl);
        };

        useEffect(() => {
            const fallback = item.url || item.originalUrl || item.mjOriginalUrl;
            const nextSrc = hasLocalCache ? localCacheFallback : fallback;
            const resolved = resolveHistoryUrl ? resolveHistoryUrl(item, nextSrc) : nextSrc;
            setVideoSrc(resolved);
        }, [item.url, item.originalUrl, item.mjOriginalUrl, hasLocalCache, localCacheFallback, resolveHistoryUrl]);

        useEffect(() => {
            if (!localCacheActive || !localCacheFallback || !onCacheMissing) return;
            if (isLocalCacheUrlAvailable && !isLocalCacheUrlAvailable(localCacheFallback)) {
                onCacheMissing(item.id, localCacheFallback);
            }
        }, [localCacheActive, localCacheFallback, item.id, onCacheMissing, isLocalCacheUrlAvailable]);

        const ratioLabel = historyMeta?.ratioLabel ?? (item.ratio || item.mjRatio);
        const resolutionLabel = historyMeta?.resolutionLabel ?? (item.resolution || (item.width && item.height ? `${item.width}x${item.height}` : null));
        const durationLabel = historyMeta?.durationLabel ?? ((item.type === 'video' && item.duration) ? `${item.duration}s` : null);
        const customParamLabels = historyMeta?.customParamLabels || [];
        const singleImageDisplayUrl = getResolvedDisplayUrl(item.url || item.originalUrl || item.mjOriginalUrl);
        const singleVideoDisplayUrl = videoSrc || item.url || item.originalUrl || item.mjOriginalUrl || '';
        const singlePreviewKey = item.type === 'video' ? singleVideoDisplayUrl : singleImageDisplayUrl;
        const [singlePreviewLoading, setSinglePreviewLoading] = useState(item.status === 'completed');
        const [singlePreviewFailed, setSinglePreviewFailed] = useState(false);
        useEffect(() => {
            setSinglePreviewLoading(item.status === 'completed');
            setSinglePreviewFailed(false);
        }, [item.id, item.type, item.status, singlePreviewKey]);
        const throttleStats = item?.throttleStats && typeof item.throttleStats === 'object' ? item.throttleStats : null;
        const throttleInfo = useMemo(() => {
            if (!throttleStats) return '';
            const info = [];
            const batchMode = String(throttleStats.imageBatchMode || '').trim();
            if (batchMode === IMAGE_BATCH_MODE_STANDARD_BATCH) info.push('标准批次');
            if (batchMode === IMAGE_BATCH_MODE_PARALLEL_AGGREGATE) info.push('并发聚合');
            const requested = Number(throttleStats.requestedImageCount || 0);
            if (requested > 1) info.push(`${requested}张`);
            const interval = Number(throttleStats.dispatchIntervalSec || 0);
            if (interval > 0) info.push(`间隔${interval}s`);
            const retries = Number(throttleStats.retryCount || 0);
            if (retries > 0) info.push(`重试×${retries}`);
            const count429 = Number(throttleStats.http429Count || 0);
            if (count429 > 0) info.push(`429×${count429}`);
            const timeoutCount = Number(throttleStats.timeoutCount || 0);
            if (timeoutCount > 0) info.push(`超时×${timeoutCount}`);
            if (throttleStats.fallbackToParallel) info.push('已回退并发');
            return info.join(' · ');
        }, [throttleStats]);
        const hasThrottleWarning = !!(throttleStats && (Number(throttleStats.http429Count || 0) > 0 || Number(throttleStats.timeoutCount || 0) > 0));

        return (
            <div className={`group rounded-lg overflow-hidden border relative cursor-pointer transition-colors ${isSelected
                ? 'border-blue-500 ring-2 ring-blue-500/30'
                : theme === 'dark' ? 'bg-zinc-900 border-zinc-800 hover:border-blue-500/50' : 'bg-white border-zinc-200 hover:border-blue-500/50'
                }`} style={{ contentVisibility: 'auto', containIntrinsicSize: '1px 300px' }} onClick={onClick} onContextMenu={onContextMenu} draggable={canDrag} onDragStart={canDrag ? (e) => handleDragStart(e) : undefined}>
                {hasLocalCache && <div className="absolute top-1 left-1 z-10 px-1 py-0.5 rounded text-[8px] bg-black/60 text-green-300">{t('本地')}</div>}
                {!hasLocalCache && performanceMode !== 'off' && thumbnailUrl && (
                    <div className={`absolute top-1 left-1 z-10 px-1 py-0.5 rounded text-[8px] bg-black/60 ${performanceMode === 'ultra' ? 'text-orange-400' : 'text-zinc-400'}`}>
                        {performanceMode === 'ultra' ? t('极速') : t('缩略')}
                    </div>
                )}
                {onSelect && (
                    <button onClick={(e) => { e.stopPropagation(); e.preventDefault(); onSelect(item.id); }} className={`absolute bottom-2 right-2 z-20 w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all ${isSelected ? 'bg-green-500 border-green-400 opacity-100' : 'border-white/60 bg-black/50 opacity-100 hover:bg-black/70'}`} title={isSelected ? t('取消选择') : t('选择')}>
                        {isSelected && <CheckCircle2 size={16} className="text-white" />}
                    </button>
                )}
                <div className={`${theme === 'dark' ? 'bg-black' : theme === 'solarized' ? 'bg-[#fafafa]' : 'bg-[#fafafa]'} relative ${((multiImages && multiImages.length > 1) || (item.mjNeedsSplit && item.apiConfig?.modelId?.includes('mj')))
                    ? (() => {
                        const ratio = item.mjRatio || '1:1';
                        if (ratio === '16:9') return 'aspect-video';
                        if (ratio === '9:16') return 'aspect-[9/16]';
                        if (ratio === '4:3') return 'aspect-[4/3]';
                        if (ratio === '3:4') return 'aspect-[3/4]';
                        if (ratio === '21:9') return 'aspect-[21/9]';
                        return 'aspect-square';
                    })()
                    : 'aspect-video'
                    }`}>
                    {item.status === 'completed' ? (
                        multiImages && multiImages.length > 1 ? (
                            <div className={`w-full h-full grid gap-0.5 p-0.5 ${multiImages.length === 4 ? 'grid-cols-2 grid-rows-2' : 'grid-cols-2'}`}>
                                {multiImages.map((imgUrl, idx) => {
                                    const cachedImgUrl = localCacheActive && item.localCacheMap ? item.localCacheMap[imgUrl] : null;
                                    const rawDisplayImgUrl = cachedImgUrl || (performanceMode !== 'off' && item.mjThumbnails && item.mjThumbnails[idx] ? item.mjThumbnails[idx] : imgUrl);
                                    const displayImgUrl = resolveHistoryUrl ? resolveHistoryUrl(item, rawDisplayImgUrl) : rawDisplayImgUrl;
                                    return (
                                        <HistoryMjImageCell
                                            key={idx}
                                            item={item}
                                            idx={idx}
                                            imgUrl={imgUrl}
                                            displayImgUrl={displayImgUrl}
                                            theme={theme}
                                            canDrag={canDrag}
                                            lightboxItem={lightboxItem}
                                            language={language}
                                            onImageClick={onImageClick}
                                            onImageContextMenu={onImageContextMenu}
                                            onCacheMissing={onCacheMissing}
                                            handleDragStart={handleDragStart}
                                        />
                                    );
                                })}
                            </div>
                        ) : (
                            item.type === 'image' ? (
                                <LazyBase64Image
                                    src={singleImageDisplayUrl}
                                    loading="lazy"
                                    className="w-full h-full object-cover"
                                    alt={item.prompt || '生成的图片'}
                                    onLoad={() => { setSinglePreviewLoading(false); setSinglePreviewFailed(false); }}
                                    onError={(e) => {
                                        const rawUrl = item.url || item.originalUrl || item.mjOriginalUrl;
                                        const resolvedUrl = getResolvedDisplayUrl(rawUrl);
                                        console.error('图片加载失败:', resolvedUrl || rawUrl);
                                        onCacheMissing && onCacheMissing(item.id, resolvedUrl || rawUrl);
                                        setSinglePreviewLoading(false);
                                        setSinglePreviewFailed(true);
                                        e.target.style.display = 'none';
                                    }}
                                />
                            ) : (
                                <ResolvedVideo
                                    src={singleVideoDisplayUrl}
                                    className="w-full h-full object-cover"
                                    muted
                                    loop
                                    playsInline
                                    preload="metadata"
                                    onLoadedMetadata={() => { setSinglePreviewLoading(false); setSinglePreviewFailed(false); }}
                                    onCanPlay={() => { setSinglePreviewLoading(false); setSinglePreviewFailed(false); }}
                                    onError={() => {
                                        const fallback = item.url || item.originalUrl || item.mjOriginalUrl;
                                        if (hasLocalCache && fallback && videoSrc === localCacheFallback) {
                                            setSinglePreviewLoading(true);
                                            setSinglePreviewFailed(false);
                                            setVideoSrc(fallback);
                                            onCacheMissing && onCacheMissing(item.id, localCacheFallback);
                                        } else {
                                            console.error('视频加载失败:', fallback);
                                            setSinglePreviewLoading(false);
                                            setSinglePreviewFailed(true);
                                        }
                                    }}
                                />
                            )
                        )
                    ) : (
                        <div className="w-full h-full flex items-center justify-center"><Loader2 className="animate-spin text-zinc-600" /></div>
                    )}
                    {item.status === 'completed' && (!multiImages || multiImages.length <= 1) && singlePreviewLoading && !singlePreviewFailed && (
                        <div className="absolute inset-0 flex items-center justify-center bg-black/35 text-white/80 text-[10px] pointer-events-none">{t('预览加载中...')}</div>
                    )}
                    {item.status === 'completed' && (!multiImages || multiImages.length <= 1) && singlePreviewFailed && (
                        <div className="absolute inset-0 flex items-center justify-center bg-black/45 text-red-200 text-[10px] px-3 text-center pointer-events-none">{t('预览加载失败（可点击进入灯箱重试）')}</div>
                    )}
                    <div className={`absolute bottom-0 left-0 right-0 h-1 ${theme === 'dark' ? 'bg-zinc-800' : 'bg-zinc-200'}`}>
                        <div className="h-full bg-blue-500 transition-all" style={{ width: `${item.progress}%` }} />
                    </div>
                </div>
                <div className={`px-3 py-2 text-[11px] ${theme === 'solarized' ? 'bg-[#eee8d5]' : ''}`}>
                    <div className="flex justify-between items-start gap-2">
                        <span className={`line-clamp-2 ${theme === 'dark' ? 'text-zinc-300' : theme === 'solarized' ? 'text-black' : 'text-zinc-700'}`}>{item.prompt || 'Untitled'}</span>
                        <div className={`shrink-0 ml-1 ${item.type === 'image' ? 'flex flex-col items-center gap-1' : 'flex items-center gap-1'}`}>
                            {item.type === 'video' && (item.status === 'generating' || item.status === 'failed') && (
                                <button onClick={(e) => { e.stopPropagation(); onRefresh && onRefresh(item); }} className={`shrink-0 p-0.5 ${theme === 'dark' ? 'text-zinc-500 hover:text-white' : 'text-zinc-400 hover:text-zinc-900'}`} title={t('刷新状态')}>
                                    <RefreshCw size={12} />
                                </button>
                            )}
                            <button onClick={(e) => { e.stopPropagation(); onDelete && onDelete(item.id); }} className={`shrink-0 p-0.5 ${theme === 'dark' ? 'text-zinc-500 hover:text-red-500' : 'text-zinc-400 hover:text-red-500'}`} title={t('删除')}><Trash2 size={12} /></button>
                            {item.type === 'image' && (
                                <button onClick={(e) => { e.stopPropagation(); onRebuildThumbnail && onRebuildThumbnail(item); }} className={`shrink-0 p-0.5 rounded ${theme === 'dark' ? 'text-blue-300 hover:text-blue-200 hover:bg-blue-500/20' : 'text-blue-500 hover:text-blue-600 hover:bg-blue-100'}`} title={t('重建缩略图')}>
                                    <RefreshCw size={12} />
                                </button>
                            )}
                        </div>
                    </div>
                    {item.status === 'failed' && item.errorMsg && (
                        <p className="text-[9px] text-red-500 mt-1 break-words whitespace-pre-wrap">
                            {item.errorMsg.split('\n').map((line, idx) => (
                                <span key={idx}>{line}{idx < item.errorMsg.split('\n').length - 1 && <br />}</span>
                            ))}
                        </p>
                    )}
                    {item.status === 'generating' && <p className="text-[9px] text-blue-500 mt-1">{item.errorMsg || '生成中...'}</p>}
                    {throttleInfo && <p className={`text-[9px] mt-1 ${hasThrottleWarning ? 'text-amber-400' : 'text-zinc-500'}`}>{throttleInfo}</p>}
                    <div className="h-1.5" />
                    <div className="flex flex-col w-full">
                        <span className={theme === 'dark' ? 'text-zinc-500' : theme === 'solarized' ? 'text-black' : 'text-zinc-400'}>
                            {(() => {
                                const hasRefImage = item.hasInputImages === true;
                                const isVideo = item.type === 'video';
                                const genType = isVideo ? (hasRefImage ? '图→视频' : '文→视频') : (hasRefImage ? '图→图' : '文→图');
                                const resDisplay = resolutionLabel;
                                return [genType, ratioLabel, resDisplay, isVideo && durationLabel ? durationLabel : null, ...customParamLabels].filter(Boolean).join(' · ');
                            })()}
                        </span>
                        <span className={theme === 'dark' ? 'text-zinc-500' : theme === 'solarized' ? 'text-black' : 'text-zinc-400'}>
                            {item.time} · <span title={modelTooltip}>{displayModelName}</span>
                            {typeof item.durationMs === 'number' && item.durationMs > 0 && <> · {t('用时')} {(item.durationMs / 1000).toFixed(1)}s</>}
                        </span>
                    </div>
                </div>
            </div>
        );
    }, (prevProps, nextProps) => (
        prevProps.item === nextProps.item &&
        prevProps.theme === nextProps.theme &&
        prevProps.lightboxItem?.id === nextProps.lightboxItem?.id &&
        prevProps.isSelected === nextProps.isSelected &&
        prevProps.performanceMode === nextProps.performanceMode &&
        prevProps.localCacheActive === nextProps.localCacheActive &&
        prevProps.getHistoryMeta === nextProps.getHistoryMeta &&
        prevProps.historyLocalCacheMap === nextProps.historyLocalCacheMap &&
        prevProps.resolveHistoryUrl === nextProps.resolveHistoryUrl &&
        prevProps.isLocalCacheUrlAvailable === nextProps.isLocalCacheUrlAvailable
    ));

    return { HistoryItem };
};

// --- Global State ---
let profiles = [];
let currentProfileId = null;
let isAdmin = false;
let adminPasscode = "";
let isPollingLogs = false;
let logPollTimer = null;
let currentActiveReport = null;
let globalTemplates = [];
let currentFeedFolder = "all";
let currentStarredFolder = "all";
let currentReportFilter = "all";
let selectedReportFolders = [];
let selectedReportKeywords = [];

function updateFolderChips(chipsContainer, rowContainer, uniqueFolders, activeFolder, onFolderSelected) {
    if (!chipsContainer || !rowContainer) return;
    chipsContainer.innerHTML = "";
    if (uniqueFolders.length === 0) {
        rowContainer.style.display = "none";
        return;
    }
    
    // Always add '전체' chip
    const allChip = document.createElement("span");
    allChip.className = `folder-chip${activeFolder === "all" ? " active" : ""}`;
    allChip.textContent = "전체";
    allChip.addEventListener("click", () => onFolderSelected("all"));
    chipsContainer.appendChild(allChip);
    
    uniqueFolders.forEach(folder => {
        const chip = document.createElement("span");
        chip.className = `folder-chip${activeFolder === folder ? " active" : ""}`;
        chip.textContent = folder;
        chip.addEventListener("click", () => onFolderSelected(folder));
        chipsContainer.appendChild(chip);
    });
    
    rowContainer.style.display = "flex";
}

function createFeedCard(item, tabType) {
    const card = document.createElement("div");
    card.className = `feed-card type-${item.type}`;
    const starClass = item.is_starred ? "active" : "";
    const starTitle = tabType === "starred" ? "중요 보관함 해제" : "중요 보관함 저장";
    const publishedDate = getPublishedDate(item);
    const collectedDate = formatDateOnly(item.created_at);
    const isAnalysisPending = item.analysis_status === "pending";
    const analysisBadge = isAnalysisPending ? `<span class="badge badge-pending">AI 요약 대기</span>` : "";
    const publishedRow = publishedDate
        ? `<span><strong>발행일</strong>${escapeHtml(formatDateOnly(publishedDate))}</span>`
        : `<span><strong>발행일</strong>확인 불가</span>`;
    const dateBlock = `
        <div class="card-date-block">
            ${publishedRow}
            <span><strong>수집일</strong>${escapeHtml(collectedDate)}</span>
        </div>
    `;
    
    if (item.type === "doc") {
        const kwTags = item.keywords ? item.keywords.split(",").map(k => `<span class="tag">${escapeHtml(k.trim())}</span>`).join("") : "";
        card.innerHTML = `
            <div class="card-header">
                <div class="card-meta">
                    <span class="badge badge-doc">경쟁사 업데이트</span>
                    ${analysisBadge}
                </div>
                <div class="card-actions">
                    <button class="feed-star-btn ${starClass}" data-id="${item.id}" data-type="doc" title="${starTitle}">★</button>
                </div>
            </div>
            <a href="${escapeHtml(item.link)}" target="_blank" class="card-title">${escapeHtml(item.title)}</a>
            ${dateBlock}
            <div class="card-impact">
                <h4>AI 요약</h4>
                <p>${escapeHtml(item.summary)}</p>
                ${item.impact ? `<small>${escapeHtml(item.impact)}</small>` : ""}
            </div>
            <div class="card-footer">
                <div class="card-tags">${kwTags}</div>
                <a href="${escapeHtml(item.link)}" target="_blank" class="card-link-btn">원문 보기 ↗</a>
            </div>
        `;
    } else {
        card.innerHTML = `
            <div class="card-header">
                <div class="card-meta">
                    <span class="badge badge-trend">기술 트렌드 뉴스</span>
                    ${analysisBadge}
                </div>
                <div class="card-actions">
                    <button class="feed-star-btn ${starClass}" data-id="${item.id}" data-type="trend" title="${starTitle}">★</button>
                </div>
            </div>
            <a href="${escapeHtml(item.link)}" target="_blank" class="card-title">${escapeHtml(item.title)}</a>
            ${dateBlock}
            <p class="card-summary">${escapeHtml(item.summary)}</p>
            <div class="card-footer">
                <div class="card-tags">
                    <span class="tag">폴더: ${escapeHtml(item.folder || "미분류")}</span>
                    <span class="tag">키워드: ${escapeHtml(item.keyword)}</span>
                    <span class="tag">출처: ${escapeHtml(item.source)}</span>
                </div>
                <a href="${escapeHtml(item.link)}" target="_blank" class="card-link-btn">원문 보기 ↗</a>
            </div>
        `;
    }
    return card;
}


// --- DOM Elements ---
const DOM = {
    profileSelect: document.getElementById("profile-select"),
    addProfileBtn: document.getElementById("add-profile-btn"),
    navItems: document.querySelectorAll(".nav-item"),
    tabPanes: document.querySelectorAll(".tab-pane"),
    connectionStatus: document.getElementById("connection-status"),
    statusTexts: document.querySelectorAll(".js-status-text"),
    statusDots: document.querySelectorAll(".js-status-dot"),
    
    // Feeds
    feedSearch: document.getElementById("feed-search"),
    feedFilterBtns: document.querySelectorAll("#feed-tab .filter-btn"),
    feedItemsGrid: document.getElementById("feed-items-grid"),
    feedEmpty: document.getElementById("feed-empty"),
    feedFolderChips: document.getElementById("feed-folder-chips"),
    feedGroupByFolder: document.getElementById("feed-group-by-folder"),
    
    // Starred
    starredSearch: document.getElementById("starred-search"),
    starredFilterBtns: document.querySelectorAll("#starred-tab .filter-btn"),
    starredItemsGrid: document.getElementById("starred-items-grid"),
    starredEmpty: document.getElementById("starred-empty"),
    compileStarredReportBtn: document.getElementById("compile-starred-report-btn"),
    starredFolderChips: document.getElementById("starred-folder-chips"),
    starredGroupByFolder: document.getElementById("starred-group-by-folder"),
    
    // Reports
    reportsListItems: document.getElementById("reports-list-items"),
    reportDetailViewer: document.getElementById("report-detail-viewer"),
    reportViewerEmpty: document.getElementById("report-viewer-empty"),
    reportViewerContent: document.getElementById("report-viewer-content"),
    reportTitleDisplay: document.getElementById("report-title-display"),
    reportDateDisplay: document.getElementById("report-date-display"),
    reportBodyDisplay: document.getElementById("report-body-display"),
    reportFilterBtns: document.querySelectorAll(".report-filter-btn"),
    generateWeeklyReportBtn: document.getElementById("generate-weekly-report-btn"),
    generateMonthlyReportBtn: document.getElementById("generate-monthly-report-btn"),
    reportAutomationStatus: document.getElementById("report-automation-status"),
    reportAutoDot: document.getElementById("report-auto-dot"),
    reportAutoTitle: document.getElementById("report-auto-title"),
    reportAutoDesc: document.getElementById("report-auto-desc"),
    goReportSettingsBtn: document.getElementById("go-report-settings-btn"),
    reportScopeFolderChips: document.getElementById("report-scope-folder-chips"),
    reportScopeKeyword: document.getElementById("report-scope-keyword"),
    reportScopeKeywordChips: document.getElementById("report-scope-keyword-chips"),
    reportKeywordMatchMode: document.getElementById("report-keyword-match-mode"),
    
    // Settings
    adminBadge: document.getElementById("admin-badge"),
    authBtn: document.getElementById("auth-btn"),
    apiKeyInput: document.getElementById("api-key-input"),
    toggleApiKeyBtn: document.getElementById("toggle-api-key"),
    webhookInput: document.getElementById("webhook-input"),
    intervalInput: document.getElementById("interval-input"),
    autoReportToggle: document.getElementById("auto-report-toggle"),
    keywordFolderSelect: document.getElementById("keyword-folder-select"),
    keywordFolderInput: document.getElementById("keyword-folder-input"),
    keywordAddInput: document.getElementById("keyword-add-input"),
    keywordTagsContainer: document.getElementById("keyword-tags-container"),
    suggestKeywordsBtn: document.getElementById("suggest-keywords-btn"),
    keywordSuggestionsPanel: document.getElementById("keyword-suggestions-panel"),
    keywordSuggestionsStatus: document.getElementById("keyword-suggestions-status"),
    keywordSuggestionsList: document.getElementById("keyword-suggestions-list"),
    keywordFolderSuggestions: document.getElementById("keyword-folder-suggestions"),
    keywordCleanupSuggestions: document.getElementById("keyword-cleanup-suggestions"),
    closeKeywordSuggestionsBtn: document.getElementById("close-keyword-suggestions-btn"),
    feedFolderFilters: document.getElementById("feed-folder-filters"),
    starredFolderFilters: document.getElementById("starred-folder-filters"),
    feedNameInput: document.getElementById("feed-name-input"),
    feedUrlInput: document.getElementById("feed-url-input"),
    addFeedRowBtn: document.getElementById("add-feed-row-btn"),
    suggestFeedsBtn: document.getElementById("suggest-feeds-btn"),
    feedSuggestionsPanel: document.getElementById("feed-suggestions-panel"),
    feedSuggestionsStatus: document.getElementById("feed-suggestions-status"),
    feedSuggestionsList: document.getElementById("feed-suggestions-list"),
    closeFeedSuggestionsBtn: document.getElementById("close-feed-suggestions-btn"),
    feedRowsContainer: document.getElementById("feed-rows-container"),
    saveSettingsBtn: document.getElementById("save-settings-btn"),
    deleteProfileBtn: document.getElementById("delete-profile-btn"),
    overviewProfileName: document.getElementById("overview-profile-name"),
    overviewKeywordCount: document.getElementById("overview-keyword-count"),
    overviewFeedCount: document.getElementById("overview-feed-count"),
    overviewScanInterval: document.getElementById("overview-scan-interval"),
    
    // Logs
    startScanBtn: document.getElementById("start-scan-btn"),
    startReportBtn: document.getElementById("start-report-btn"),
    stopProcessBtn: document.getElementById("stop-process-btn"),
    terminalOutputBody: document.getElementById("terminal-output-body"),
    clearLogsBtn: document.getElementById("clear-logs-btn"),
    
    // Modals
    addProfileModal: document.getElementById("add-profile-modal"),
    newProfileNameInput: document.getElementById("new-profile-name"),
    closeProfileModalBtn: document.getElementById("close-profile-modal-btn"),
    cancelProfileModalBtn: document.getElementById("cancel-profile-modal-btn"),
    confirmProfileModalBtn: document.getElementById("confirm-profile-modal-btn"),
    
    authModal: document.getElementById("auth-modal"),
    adminPasscodeInput: document.getElementById("admin-passcode-input"),
    closeAuthModalBtn: document.getElementById("close-auth-modal-btn"),
    cancelAuthModalBtn: document.getElementById("cancel-auth-modal-btn"),
    confirmAuthModalBtn: document.getElementById("confirm-auth-modal-btn"),

    // Board
    boardTitleInput: document.getElementById("board-title-input"),
    boardContentInput: document.getElementById("board-content-input"),
    submitPostBtn: document.getElementById("submit-post-btn"),
    boardPostsContainer: document.getElementById("board-posts-container"),

    // Templates
    templateTypeSelect: document.getElementById("template-type-select"),
    customTemplateGroup: document.getElementById("custom-template-group"),
    customTemplateInput: document.getElementById("custom-template-input"),
    adminTemplatesConsole: document.getElementById("admin-templates-console"),
    globalTemplateSelect: document.getElementById("global-template-select"),
    globalTemplateContentInput: document.getElementById("global-template-content-input"),
    saveGlobalTemplateBtn: document.getElementById("save-global-template-btn"),
    
    // Downloads
    downloadMdBtn: document.getElementById("download-md-btn"),
    downloadPdfBtn: document.getElementById("download-pdf-btn"),
    reportViewerContent: document.getElementById("report-viewer-content"),
};

// --- Initialization ---
document.addEventListener("DOMContentLoaded", async () => {
    setupTabNavigation();
    setupEventListeners();
    await checkAuthStatus();
    await loadProfiles();
    await loadGlobalTemplates();
    startLogPolling();
    
    // Dynamic Team URL rendering in Guide tab
    const host = window.location.host;
    const teamUrlEl = document.getElementById("guide-team-url");
    if (teamUrlEl) {
        teamUrlEl.textContent = `http://${host}`;
    }
});

// --- Tab Navigation Setup ---
function setupTabNavigation() {
    DOM.navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const tabId = item.getAttribute("data-tab");
            
            // Update Active Nav Link
            DOM.navItems.forEach(nav => nav.classList.remove("active"));
            item.classList.add("active");
            
            // Update Active Tab Pane
            DOM.tabPanes.forEach(pane => {
                pane.classList.remove("active");
                if (pane.id === `${tabId}-tab`) {
                    pane.classList.add("active");
                }
            });
            
            // Tab Specific Actions
            if (tabId === "feed") {
                loadFeeds();
            } else if (tabId === "starred") {
                loadStarredFeeds();
            } else if (tabId === "reports") {
                loadReports();
            } else if (tabId === "board") {
                loadBoardPosts();
            }
        });
    });
}

// --- Event Listeners Setup ---
function setupEventListeners() {
    // Profile Selection
    DOM.profileSelect.addEventListener("change", (e) => {
        currentProfileId = parseInt(e.target.value);
        onProfileChanged();
    });
    
    // Open Add Profile Modal
    DOM.addProfileBtn.addEventListener("click", () => {
        DOM.newProfileNameInput.value = "";
        DOM.addProfileModal.style.display = "flex";
    });
    
    // Close Add Profile Modal
    DOM.closeProfileModalBtn.addEventListener("click", () => DOM.addProfileModal.style.display = "none");
    DOM.cancelProfileModalBtn.addEventListener("click", () => DOM.addProfileModal.style.display = "none");
    
    // Confirm Add Profile
    DOM.confirmProfileModalBtn.addEventListener("click", handleAddProfile);
    
    // Authentication Unlock
    DOM.authBtn.addEventListener("click", () => {
        if (isAdmin) {
            // Log out/Lock back
            isAdmin = false;
            adminPasscode = "";
            updateAdminControls();
        } else {
            DOM.adminPasscodeInput.value = "";
            DOM.authModal.style.display = "flex";
        }
    });
    
    // Close Auth Modal
    DOM.closeAuthModalBtn.addEventListener("click", () => DOM.authModal.style.display = "none");
    DOM.cancelAuthModalBtn.addEventListener("click", () => DOM.authModal.style.display = "none");
    DOM.confirmAuthModalBtn.addEventListener("click", handleAuthVerify);
    
    // Save Settings
    DOM.saveSettingsBtn.addEventListener("click", handleSaveSettings);
    
    // Delete Profile
    DOM.deleteProfileBtn.addEventListener("click", handleDeleteProfile);
    
    // Keywords Actions
    if (DOM.keywordFolderSelect) {
        DOM.keywordFolderSelect.addEventListener("change", () => {
            if (DOM.keywordFolderSelect.value === "__new__") {
                DOM.keywordFolderInput.style.display = "block";
                DOM.keywordFolderInput.focus();
            } else {
                DOM.keywordFolderInput.style.display = "none";
                DOM.keywordFolderInput.value = "";
            }
        });
    }

    DOM.keywordAddInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && DOM.keywordAddInput.value.trim()) {
            const keyword = DOM.keywordAddInput.value.trim();
            let folder = "미분류";
            if (DOM.keywordFolderSelect && DOM.keywordFolderSelect.value !== "__new__") {
                folder = DOM.keywordFolderSelect.value;
            } else if (DOM.keywordFolderInput) {
                folder = DOM.keywordFolderInput.value.trim() || "미분류";
            }
            
            addKeywordTag(keyword, folder);
            
            // On-the-fly add to select options
            if (folder && folder !== "미분류" && DOM.keywordFolderSelect) {
                let exists = false;
                Array.from(DOM.keywordFolderSelect.options).forEach(opt => {
                    if (opt.value === folder) exists = true;
                });
                if (!exists) {
                    const opt = document.createElement("option");
                    opt.value = folder;
                    opt.textContent = folder;
                    DOM.keywordFolderSelect.insertBefore(opt, DOM.keywordFolderSelect.lastElementChild);
                }
                DOM.keywordFolderSelect.value = folder;
                DOM.keywordFolderInput.style.display = "none";
                DOM.keywordFolderInput.value = "";
            } else if (DOM.keywordFolderSelect) {
                DOM.keywordFolderSelect.value = "미분류";
                DOM.keywordFolderInput.style.display = "none";
                DOM.keywordFolderInput.value = "";
            }
            
            DOM.keywordAddInput.value = "";
        }
    });

    if (DOM.suggestKeywordsBtn) {
        DOM.suggestKeywordsBtn.addEventListener("click", handleSuggestKeywords);
    }
    if (DOM.closeKeywordSuggestionsBtn) {
        DOM.closeKeywordSuggestionsBtn.addEventListener("click", () => {
            DOM.keywordSuggestionsPanel.style.display = "none";
        });
    }
    if (DOM.suggestFeedsBtn) {
        DOM.suggestFeedsBtn.addEventListener("click", handleSuggestFeeds);
    }
    if (DOM.closeFeedSuggestionsBtn) {
        DOM.closeFeedSuggestionsBtn.addEventListener("click", () => {
            DOM.feedSuggestionsPanel.style.display = "none";
        });
    }
    
    // Feeds Actions
    DOM.addFeedRowBtn.addEventListener("click", () => {
        const name = DOM.feedNameInput.value.trim();
        const url = DOM.feedUrlInput.value.trim();
        if (name && url) {
            addFeedRow(name, url);
            DOM.feedNameInput.value = "";
            DOM.feedUrlInput.value = "";
        }
    });
    
    // Password Visibility
    DOM.toggleApiKeyBtn.addEventListener("click", () => {
        const type = DOM.apiKeyInput.type === "password" ? "text" : "password";
        DOM.apiKeyInput.type = type;
        DOM.toggleApiKeyBtn.textContent = type === "password" ? "👁️" : "🙈";
    });
    
    // Feed Search & Filtering
    DOM.feedSearch.addEventListener("input", debounce(() => loadFeeds(), 300));
    if (DOM.feedGroupByFolder) {
        DOM.feedGroupByFolder.addEventListener("change", () => loadFeeds());
    }
    
    DOM.feedFilterBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            DOM.feedFilterBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            loadFeeds();
        });
    });

    // Starred Search & Filtering
    if (DOM.starredSearch) {
        DOM.starredSearch.addEventListener("input", debounce(() => loadStarredFeeds(), 300));
    }
    if (DOM.starredGroupByFolder) {
        DOM.starredGroupByFolder.addEventListener("change", () => loadStarredFeeds());
    }
    
    DOM.starredFilterBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            DOM.starredFilterBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            loadStarredFeeds();
        });
    });

    if (DOM.compileStarredReportBtn) {
        DOM.compileStarredReportBtn.addEventListener("click", handleCompileStarredReport);
    }

    DOM.reportFilterBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            DOM.reportFilterBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentReportFilter = btn.getAttribute("data-report-filter") || "all";
            loadReports();
        });
    });

    if (DOM.generateWeeklyReportBtn) {
        DOM.generateWeeklyReportBtn.addEventListener("click", () => handleGenerateReport("weekly"));
    }
    if (DOM.generateMonthlyReportBtn) {
        DOM.generateMonthlyReportBtn.addEventListener("click", () => handleGenerateReport("monthly"));
    }
    if (DOM.reportScopeKeyword) {
        DOM.reportScopeKeyword.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && DOM.reportScopeKeyword.value.trim()) {
                e.preventDefault();
                addReportKeyword(DOM.reportScopeKeyword.value.trim());
                DOM.reportScopeKeyword.value = "";
            }
        });
    }
    if (DOM.goReportSettingsBtn) {
        DOM.goReportSettingsBtn.addEventListener("click", () => {
            const settingsTab = Array.from(DOM.navItems).find(nav => nav.getAttribute("data-tab") === "settings");
            if (settingsTab) settingsTab.click();
        });
    }
    
    // Log controls
    DOM.startScanBtn.addEventListener("click", () => triggerBackgroundRun("/api/scan"));
    DOM.startReportBtn.addEventListener("click", () => triggerBackgroundRun(`/api/report/generate?profile_id=${currentProfileId}&report_type=monthly`));
    DOM.stopProcessBtn.addEventListener("click", stopBackgroundRun);
    DOM.clearLogsBtn.addEventListener("click", () => DOM.terminalOutputBody.innerHTML = "");
    
    // Board actions
    DOM.submitPostBtn.addEventListener("click", handleCreateBoardPost);
    
    // Template toggles
    DOM.templateTypeSelect.addEventListener("change", (e) => {
        DOM.customTemplateGroup.style.display = e.target.value === "custom" ? "block" : "none";
    });
    
    // Global templates events
    DOM.globalTemplateSelect.addEventListener("change", onGlobalTemplateChanged);
    DOM.saveGlobalTemplateBtn.addEventListener("click", handleSaveGlobalTemplate);
    
    // Downloads events
    DOM.downloadMdBtn.addEventListener("click", () => {
        if (!currentActiveReport) return;
        downloadTextFile(`${currentActiveReport.title}.md`, currentActiveReport.content);
    });
    DOM.downloadPdfBtn.addEventListener("click", () => {
        if (!currentActiveReport) return;
        exportReportToPdf(currentActiveReport.title);
    });
}

// --- Auth Manager ---
async function checkAuthStatus() {
    try {
        const res = await fetch("/api/auth/check");
        const data = await res.json();
        isAdmin = data.is_admin;
        updateAdminControls();
        DOM.connectionStatus.textContent = "서버 연결 완료";
        DOM.connectionStatus.style.color = "var(--color-success)";
    } catch (e) {
        DOM.connectionStatus.textContent = "서버 오프라인";
        DOM.connectionStatus.style.color = "var(--color-danger)";
    }
}

async function handleAuthVerify() {
    const passcode = DOM.adminPasscodeInput.value.trim();
    if (!passcode) return;
    
    try {
        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ passcode })
        });
        
        if (res.ok) {
            isAdmin = true;
            adminPasscode = passcode;
            updateAdminControls();
            DOM.authModal.style.display = "none";
            alert("관리자 권한이 활성화되었습니다.");
        } else {
            alert("잘못된 관리자 비밀번호입니다.");
        }
    } catch (e) {
        alert("인증 오류가 발생했습니다.");
    }
}

function updateAdminControls() {
    if (isAdmin) {
        DOM.adminBadge.className = "badge badge-unlocked";
        DOM.adminBadge.textContent = "🔓 슈퍼 관리자 모드";
        DOM.authBtn.textContent = "권한 잠그기";
        
        // Enable Controls
        DOM.apiKeyInput.removeAttribute("disabled");
        DOM.webhookInput.removeAttribute("disabled");
        DOM.intervalInput.removeAttribute("disabled");
        if (DOM.autoReportToggle) DOM.autoReportToggle.removeAttribute("disabled");
        if (DOM.keywordFolderInput) DOM.keywordFolderInput.removeAttribute("disabled");
        if (DOM.keywordFolderSelect) DOM.keywordFolderSelect.removeAttribute("disabled");
        DOM.keywordAddInput.removeAttribute("disabled");
        if (DOM.suggestKeywordsBtn) {
            DOM.suggestKeywordsBtn.classList.remove("disabled");
            DOM.suggestKeywordsBtn.removeAttribute("disabled");
        }
        DOM.feedNameInput.removeAttribute("disabled");
        DOM.feedUrlInput.removeAttribute("disabled");
        DOM.addFeedRowBtn.classList.remove("disabled");
        DOM.addFeedRowBtn.removeAttribute("disabled");
        if (DOM.suggestFeedsBtn) {
            DOM.suggestFeedsBtn.classList.remove("disabled");
            DOM.suggestFeedsBtn.removeAttribute("disabled");
        }
        DOM.saveSettingsBtn.classList.remove("disabled");
        DOM.saveSettingsBtn.removeAttribute("disabled");
        DOM.deleteProfileBtn.classList.remove("disabled");
        DOM.deleteProfileBtn.removeAttribute("disabled");
        
        DOM.templateTypeSelect.removeAttribute("disabled");
        DOM.customTemplateInput.removeAttribute("disabled");
        DOM.adminTemplatesConsole.style.display = "grid";
    } else {
        DOM.adminBadge.className = "badge badge-locked";
        DOM.adminBadge.textContent = "🔒 일반 접근 모드";
        DOM.authBtn.textContent = "자격 증명 잠금해제";
        
        // Disable sensitive settings (Admin Only)
        DOM.apiKeyInput.setAttribute("disabled", "true");
        DOM.webhookInput.setAttribute("disabled", "true");
        DOM.intervalInput.setAttribute("disabled", "true");
        if (DOM.autoReportToggle) DOM.autoReportToggle.setAttribute("disabled", "true");
        DOM.deleteProfileBtn.classList.add("disabled");
        DOM.deleteProfileBtn.setAttribute("disabled", "true");
        
        // Enable user profile settings (Keywords, Feeds, Templates)
        if (DOM.keywordFolderInput) DOM.keywordFolderInput.removeAttribute("disabled");
        if (DOM.keywordFolderSelect) DOM.keywordFolderSelect.removeAttribute("disabled");
        DOM.keywordAddInput.removeAttribute("disabled");
        if (DOM.suggestKeywordsBtn) {
            DOM.suggestKeywordsBtn.classList.remove("disabled");
            DOM.suggestKeywordsBtn.removeAttribute("disabled");
        }
        DOM.feedNameInput.removeAttribute("disabled");
        DOM.feedUrlInput.removeAttribute("disabled");
        if (DOM.suggestFeedsBtn) {
            DOM.suggestFeedsBtn.classList.remove("disabled");
            DOM.suggestFeedsBtn.removeAttribute("disabled");
        }
        
        DOM.addFeedRowBtn.classList.remove("disabled");
        DOM.addFeedRowBtn.removeAttribute("disabled");
        
        DOM.saveSettingsBtn.classList.remove("disabled");
        DOM.saveSettingsBtn.removeAttribute("disabled");
        
        DOM.templateTypeSelect.removeAttribute("disabled");
        DOM.customTemplateInput.removeAttribute("disabled");
        
        DOM.adminTemplatesConsole.style.display = "none";
    }
}

// --- Profiles Loader ---
async function loadProfiles() {
    try {
        const res = await fetch("/api/profiles");
        profiles = await res.json();
        
        // Populate dropdown
        DOM.profileSelect.innerHTML = "";
        profiles.forEach(p => {
            const opt = document.createElement("option");
            opt.value = p.id;
            opt.textContent = p.name;
            DOM.profileSelect.appendChild(opt);
        });
        
        if (profiles.length > 0) {
            // Select first profile if none currently selected
            if (!currentProfileId || !profiles.some(p => p.id === currentProfileId)) {
                currentProfileId = profiles[0].id;
            }
            DOM.profileSelect.value = currentProfileId;
            onProfileChanged();
        }
    } catch (e) {
        console.error("Failed to load profiles:", e);
    }
}

function onProfileChanged() {
    const profile = profiles.find(p => p.id === currentProfileId);
    if (!profile) return;
    
    // Load Settings view fields
    DOM.apiKeyInput.value = profile.gemini_api_key || "";
    DOM.webhookInput.value = profile.discord_webhook_url || "";
    DOM.intervalInput.value = profile.check_interval_hours || 24;
    if (DOM.autoReportToggle) {
        DOM.autoReportToggle.checked = profile.auto_report_enabled !== 0;
    }
    updateReportAutomationStatus(profile);
    
    // Load dynamic templates settings
    const templateType = profile.report_template_type || "basic";
    DOM.templateTypeSelect.value = templateType;
    DOM.customTemplateInput.value = profile.custom_report_template || "";
    DOM.customTemplateGroup.style.display = templateType === "custom" ? "block" : "none";
    
    // Populate folders dropdown in Settings
    if (DOM.keywordFolderSelect) {
        DOM.keywordFolderSelect.innerHTML = "";
        
        // Default "미분류" option
        const optDefault = document.createElement("option");
        optDefault.value = "미분류";
        optDefault.textContent = "폴더: 미분류";
        DOM.keywordFolderSelect.appendChild(optDefault);
        
        // Add existing folders from profile keywords
        const uniqueFolders = Array.from(new Set(profile.keywords.map(k => k.folder || "미분류").filter(f => f && f !== "미분류")));
        uniqueFolders.forEach(folder => {
            const opt = document.createElement("option");
            opt.value = folder;
            opt.textContent = folder;
            DOM.keywordFolderSelect.appendChild(opt);
        });
        
        // Add new folder trigger option
        const optNew = document.createElement("option");
        optNew.value = "__new__";
        optNew.textContent = "+ 새 폴더 직접 입력...";
        DOM.keywordFolderSelect.appendChild(optNew);
        
        DOM.keywordFolderSelect.value = "미분류";
        DOM.keywordFolderInput.style.display = "none";
        DOM.keywordFolderInput.value = "";
    }
    populateReportScopeFolders(profile);

    // Keywords tags rendering
    DOM.keywordTagsContainer.innerHTML = "";
    profile.keywords.forEach(kw => addKeywordTagElement(kw));
    
    // Feeds rows rendering
    DOM.feedRowsContainer.innerHTML = "";
    profile.feeds.forEach(f => addFeedRowElement(f.name, f.feed_url));
    updateSettingsOverview(profile);
    updateAdminControls();
    
    // Trigger reloading feeds and reports on active pane
    const activeTab = document.querySelector(".nav-item.active").getAttribute("data-tab");
    if (activeTab === "feed") {
        loadFeeds();
    } else if (activeTab === "starred") {
        loadStarredFeeds();
    } else if (activeTab === "reports") {
        loadReports();
    }
}

function updateReportAutomationStatus(profile) {
    if (!profile || !DOM.reportAutoTitle || !DOM.reportAutoDesc || !DOM.reportAutoDot) return;
    
    const enabled = profile.auto_report_enabled !== 0;
    DOM.reportAutoDot.className = `automation-status-dot ${enabled ? "on" : "off"}`;
    if (enabled) {
        DOM.reportAutoTitle.textContent = "자동 보고서 생성 ON";
        DOM.reportAutoDesc.textContent = "스캔 후 주간/월간 보고서를 자동으로 아카이빙하고 Discord 알림을 전송합니다.";
    } else {
        DOM.reportAutoTitle.textContent = "자동 보고서 생성 OFF";
        DOM.reportAutoDesc.textContent = "데이터 수집만 자동으로 진행되며, 보고서는 상단 버튼으로 수동 생성합니다.";
    }
}

function updateSettingsOverview(profile) {
    if (!profile) return;
    const keywordCount = profile.keywords ? profile.keywords.length : 0;
    const feedCount = profile.feeds ? profile.feeds.length : 0;
    const interval = profile.check_interval_hours || 24;
    
    if (DOM.overviewProfileName) DOM.overviewProfileName.textContent = profile.name || "-";
    if (DOM.overviewKeywordCount) DOM.overviewKeywordCount.textContent = `${keywordCount}개`;
    if (DOM.overviewFeedCount) DOM.overviewFeedCount.textContent = `${feedCount}개`;
    if (DOM.overviewScanInterval) DOM.overviewScanInterval.textContent = `${interval}시간`;
}

async function handleAddProfile() {
    const name = DOM.newProfileNameInput.value.trim();
    if (!name) return;
    
    try {
        const res = await fetch("/api/profiles", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name })
        });
        
        if (res.ok) {
            const data = await res.json();
            currentProfileId = data.id;
            DOM.addProfileModal.style.display = "none";
            await loadProfiles();
            alert(`프로필 '${name}'이 생성되었습니다.`);
        } else {
            const err = await res.json();
            alert(`프로필 생성 실패: ${err.detail}`);
        }
    } catch (e) {
        alert("오류가 발생했습니다.");
    }
}

async function handleDeleteProfile() {
    const profile = profiles.find(p => p.id === currentProfileId);
    if (!profile) return;
    
    if (profiles.length <= 1) {
        alert("최소 1개의 프로필은 존재해야 합니다.");
        return;
    }
    
    if (!confirm(`정말로 프로필 '${profile.name}'을 삭제하시겠습니까?\n프로필 내의 모든 데이터와 로그가 영구 삭제됩니다.`)) {
        return;
    }
    
    try {
        const headers = {};
        if (adminPasscode) headers["X-Admin-Passcode"] = adminPasscode;
        
        const res = await fetch(`/api/profiles/${currentProfileId}`, {
            method: "DELETE",
            headers
        });
        
        if (res.ok) {
            alert("프로필이 성공적으로 삭제되었습니다.");
            currentProfileId = null;
            await loadProfiles();
        } else {
            const err = await res.json();
            alert(`프로필 삭제 실패: ${err.detail}`);
        }
    } catch (e) {
        alert("삭제 처리 중 오류가 발생했습니다.");
    }
}

// --- Settings Modifiers (UI helpers) ---

function addKeywordTagElement(keyword) {
    let kwText = "";
    let folderText = "미분류";
    
    if (typeof keyword === "object" && keyword !== null) {
        kwText = keyword.keyword;
        folderText = keyword.folder || "미분류";
    } else {
        kwText = keyword;
    }
    
    // Find or create folder group container inside keywordTagsContainer
    let folderGroup = DOM.keywordTagsContainer.querySelector(`.folder-group[data-folder="${escapeHtml(folderText)}"]`);
    if (!folderGroup) {
        folderGroup = document.createElement("div");
        folderGroup.className = "folder-group";
        folderGroup.setAttribute("data-folder", folderText);
        folderGroup.innerHTML = `
            <div class="folder-group-header">
                <span class="folder-icon">📁</span>
                <span class="folder-name">${escapeHtml(folderText)}</span>
            </div>
            <div class="folder-group-tags"></div>
        `;
        DOM.keywordTagsContainer.appendChild(folderGroup);
    }
    
    const tagsContainer = folderGroup.querySelector(".folder-group-tags");
    
    const tag = document.createElement("span");
    tag.className = "keyword-tag";
    tag.setAttribute("data-keyword", kwText);
    tag.setAttribute("data-folder", folderText);
    tag.innerHTML = `${escapeHtml(kwText)} <span class="remove-tag">&times;</span>`;
    
    // Remove handler
    tag.querySelector(".remove-tag").addEventListener("click", () => {
        removeKeywordTagAndEmptyGroup(tag);
    });
    
    tagsContainer.appendChild(tag);
}

function addKeywordTag(keyword, folder = "미분류") {
    if (!keyword) return;
    // Check duplicates
    const tags = Array.from(DOM.keywordTagsContainer.querySelectorAll(".keyword-tag")).map(t => t.getAttribute("data-keyword"));
    if (tags.includes(keyword)) return;
    addKeywordTagElement({ keyword, folder });
}

function getCurrentKeywordPayload() {
    return Array.from(DOM.keywordTagsContainer.querySelectorAll(".keyword-tag"))
                .map(t => ({
                    keyword: t.getAttribute("data-keyword"),
                    folder: t.getAttribute("data-folder") || "미분류"
                }));
}

function ensureFolderOption(folder) {
    if (!folder || !DOM.keywordFolderSelect) return;
    const exists = Array.from(DOM.keywordFolderSelect.options).some(opt => opt.value === folder);
    if (!exists) {
        const opt = document.createElement("option");
        opt.value = folder;
        opt.textContent = folder;
        DOM.keywordFolderSelect.insertBefore(opt, DOM.keywordFolderSelect.lastElementChild);
    }
}

async function handleSuggestKeywords() {
    if (!currentProfileId || !DOM.keywordSuggestionsPanel) return;
    const seedKeyword = DOM.keywordAddInput.value.trim();
    const keywords = getCurrentKeywordPayload();
    
    DOM.keywordSuggestionsPanel.style.display = "block";
    DOM.keywordSuggestionsStatus.textContent = "AI가 연관 키워드와 폴더를 분석 중입니다...";
    DOM.keywordSuggestionsList.innerHTML = "";
    DOM.keywordFolderSuggestions.innerHTML = "";
    DOM.keywordCleanupSuggestions.innerHTML = "";
    DOM.suggestKeywordsBtn.setAttribute("disabled", "true");
    DOM.suggestKeywordsBtn.classList.add("disabled");
    
    try {
        const res = await fetch("/api/keywords/suggest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                profile_id: currentProfileId,
                seed_keyword: seedKeyword,
                keywords
            })
        });
        
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "추천을 가져오지 못했습니다.");
        }
        
        const data = await res.json();
        renderKeywordSuggestions(data);
    } catch (e) {
        DOM.keywordSuggestionsStatus.textContent = `추천 실패: ${e.message}`;
    } finally {
        DOM.suggestKeywordsBtn.removeAttribute("disabled");
        DOM.suggestKeywordsBtn.classList.remove("disabled");
    }
}

function renderKeywordSuggestions(data) {
    const suggestions = data.suggestions || [];
    const folderSuggestions = data.folder_suggestions || [];
    const cleanupSuggestions = data.cleanup_suggestions || [];
    
    DOM.keywordSuggestionsStatus.textContent = suggestions.length
        ? "추가할 키워드를 선택하세요. 추가 후에는 프로필 설정 저장을 눌러야 반영됩니다."
        : "새로 추천할 키워드가 많지 않습니다. 입력한 키워드를 조금 더 구체화해보세요.";
    
    DOM.keywordSuggestionsList.innerHTML = suggestions.length ? `
        <div class="suggestions-bulk-actions">
            <button type="button" class="btn secondary tiny" id="add-all-suggested-keywords-btn">추천 키워드 모두 추가</button>
            <span>AI 추천 ${suggestions.length}개</span>
        </div>
        ${suggestions.map((item, idx) => `
        <div class="keyword-suggestion-card">
            <div>
                <strong>${escapeHtml(item.keyword)}</strong>
                <span class="suggestion-folder">${escapeHtml(item.folder || "미분류")}</span>
                <p>${escapeHtml(item.reason || "연관 모니터링 키워드로 추천됩니다.")}</p>
            </div>
            <button type="button" class="btn tiny add-suggested-keyword" data-index="${idx}">추가</button>
        </div>
    `).join("")}
    ` : "";

    const addAllBtn = document.getElementById("add-all-suggested-keywords-btn");
    if (addAllBtn) {
        addAllBtn.addEventListener("click", () => {
            let addedCount = 0;
            suggestions.forEach(item => {
                if (addSuggestedKeyword(item)) addedCount += 1;
            });
            DOM.keywordSuggestionsList.querySelectorAll(".add-suggested-keyword").forEach(btn => {
                btn.textContent = "추가됨";
                btn.setAttribute("disabled", "true");
            });
            addAllBtn.textContent = addedCount ? `${addedCount}개 추가됨` : "이미 모두 추가됨";
            addAllBtn.setAttribute("disabled", "true");
        });
    }
    
    DOM.keywordSuggestionsList.querySelectorAll(".add-suggested-keyword").forEach(btn => {
        btn.addEventListener("click", () => {
            const item = suggestions[Number(btn.dataset.index)];
            if (!item) return;
            if (addSuggestedKeyword(item)) {
                btn.textContent = "추가됨";
                btn.setAttribute("disabled", "true");
            } else {
                btn.textContent = "이미 있음";
                btn.setAttribute("disabled", "true");
            }
        });
    });
    
    DOM.keywordFolderSuggestions.innerHTML = folderSuggestions.length ? `
        <div class="suggestion-section-title">추천 폴더</div>
        ${folderSuggestions.map(item => `
            <div class="suggestion-note">
                <strong>${escapeHtml(item.folder || "")}</strong>
                <span>${escapeHtml(item.reason || "")}</span>
            </div>
        `).join("")}
    ` : "";
    
    DOM.keywordCleanupSuggestions.innerHTML = cleanupSuggestions.length ? `
        <div class="suggestions-bulk-actions">
            <div class="suggestion-section-title">중복/표기 정리 제안</div>
            <button type="button" class="cleanup-apply-btn" id="apply-keyword-cleanup-btn">정리 제안 적용</button>
        </div>
        ${cleanupSuggestions.map(item => `
            <div class="suggestion-note">
                <strong>${escapeHtml(item.canonical || "")}</strong>
                <span>${escapeHtml((item.duplicates || []).join(", "))} ${item.reason ? "· " + escapeHtml(item.reason) : ""}</span>
            </div>
        `).join("")}
    ` : "";

    const cleanupBtn = document.getElementById("apply-keyword-cleanup-btn");
    if (cleanupBtn) {
        cleanupBtn.addEventListener("click", () => {
            const preview = cleanupSuggestions
                .map(item => `${(item.duplicates || []).join(", ")} -> ${item.canonical}`)
                .join("\n");
            if (!confirm(`다음 중복/표기 정리 제안을 적용할까요?\n\n${preview}\n\n적용 후에는 프로필 설정 변경 저장을 눌러야 DB에 반영됩니다.`)) {
                return;
            }
            const result = applyKeywordCleanupSuggestions(cleanupSuggestions);
            cleanupBtn.textContent = `${result.changed}개 정리됨`;
            cleanupBtn.setAttribute("disabled", "true");
            DOM.keywordSuggestionsStatus.textContent = `정리 제안을 적용했습니다. ${result.changed}개 키워드가 정리되었고, ${result.removed}개 중복 태그가 제거되었습니다. 저장 버튼을 눌러 반영하세요.`;
        });
    }
}

function addSuggestedKeyword(item) {
    if (!item || !item.keyword) return false;
    const existing = Array.from(DOM.keywordTagsContainer.querySelectorAll(".keyword-tag"))
                          .map(t => (t.getAttribute("data-keyword") || "").toLowerCase());
    if (existing.includes(item.keyword.toLowerCase())) return false;
    const folder = item.folder || "미분류";
    ensureFolderOption(folder);
    addKeywordTag(item.keyword, folder);
    return true;
}

function applyKeywordCleanupSuggestions(cleanupSuggestions) {
    let changed = 0;
    let removed = 0;
    
    cleanupSuggestions.forEach(item => {
        const canonical = (item.canonical || "").trim();
        const duplicates = (item.duplicates || []).map(d => String(d).trim()).filter(Boolean);
        if (!canonical || duplicates.length === 0) return;
        
        const tags = Array.from(DOM.keywordTagsContainer.querySelectorAll(".keyword-tag"));
        const canonicalTag = tags.find(tag => (tag.getAttribute("data-keyword") || "").toLowerCase() === canonical.toLowerCase());
        const duplicateTags = tags.filter(tag => duplicates.some(dup => (tag.getAttribute("data-keyword") || "").toLowerCase() === dup.toLowerCase()));
        
        if (canonicalTag) {
            duplicateTags.forEach(tag => {
                if (tag !== canonicalTag) {
                    removeKeywordTagAndEmptyGroup(tag);
                    removed += 1;
                }
            });
            changed += duplicateTags.length ? 1 : 0;
            return;
        }
        
        const targetTag = duplicateTags[0];
        if (!targetTag) return;
        const folder = targetTag.getAttribute("data-folder") || "미분류";
        removeKeywordTagAndEmptyGroup(targetTag);
        addKeywordTag(canonical, folder);
        changed += 1;
        
        duplicateTags.slice(1).forEach(tag => {
            removeKeywordTagAndEmptyGroup(tag);
            removed += 1;
        });
    });
    
    return { changed, removed };
}

function getCurrentFeedPayload() {
    return Array.from(DOM.feedRowsContainer.querySelectorAll("tr")).map(row => {
        const cols = row.querySelectorAll("td");
        return {
            name: cols[0] ? cols[0].textContent.trim() : "",
            feed_url: cols[1] ? cols[1].textContent.trim() : ""
        };
    }).filter(item => item.name && item.feed_url);
}

async function handleSuggestFeeds() {
    if (!currentProfileId || !DOM.feedSuggestionsPanel) return;
    const seedTopic = [DOM.feedNameInput.value.trim(), DOM.feedUrlInput.value.trim()]
        .filter(Boolean)
        .join(" ");
    const keywords = getCurrentKeywordPayload();
    const feeds = getCurrentFeedPayload();
    
    DOM.feedSuggestionsPanel.style.display = "block";
    DOM.feedSuggestionsStatus.textContent = "AI가 경쟁제품/공식 문서/RSS 후보를 찾고, URL 접속 검증을 진행 중입니다...";
    DOM.feedSuggestionsList.innerHTML = "";
    DOM.suggestFeedsBtn.setAttribute("disabled", "true");
    DOM.suggestFeedsBtn.classList.add("disabled");
    
    try {
        const res = await fetch("/api/feeds/suggest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                profile_id: currentProfileId,
                seed_topic: seedTopic,
                keywords,
                feeds
            })
        });
        
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "추천 피드를 가져오지 못했습니다.");
        }
        
        const data = await res.json();
        renderFeedSuggestions(data);
    } catch (e) {
        DOM.feedSuggestionsStatus.textContent = `추천 실패: ${e.message}`;
    } finally {
        DOM.suggestFeedsBtn.removeAttribute("disabled");
        DOM.suggestFeedsBtn.classList.remove("disabled");
    }
}

function renderFeedSuggestions(data) {
    const suggestions = data.suggestions || [];
    const verified = suggestions.filter(item => item.validation && item.validation.status === "verified");
    
    DOM.feedSuggestionsStatus.textContent = suggestions.length
        ? `총 ${suggestions.length}개 후보 중 ${verified.length}개 URL이 검증되었습니다. 검증된 항목만 바로 추가할 수 있습니다.`
        : "추천할 새 피드 후보가 많지 않습니다. 키워드나 제품명을 조금 더 구체화해보세요.";
    
    DOM.feedSuggestionsList.innerHTML = suggestions.length ? `
        <div class="suggestions-bulk-actions feed-bulk-actions">
            <button type="button" class="feed-bulk-add-btn" id="add-all-verified-feeds-btn" ${verified.length ? "" : "disabled"}>검증된 항목 일괄 추가</button>
            <span>검증 완료 ${verified.length}개</span>
        </div>
        ${suggestions.map((item, idx) => renderFeedSuggestionCard(item, idx)).join("")}
    ` : "";

    const addAllBtn = document.getElementById("add-all-verified-feeds-btn");
    if (addAllBtn) {
        addAllBtn.addEventListener("click", () => {
            let addedCount = 0;
            suggestions.forEach(item => {
                if (item.validation && item.validation.status === "verified" && addSuggestedFeed(item)) {
                    addedCount += 1;
                }
            });
            DOM.feedSuggestionsList.querySelectorAll(".add-suggested-feed").forEach(btn => {
                btn.textContent = "처리됨";
                btn.setAttribute("disabled", "true");
            });
            addAllBtn.textContent = addedCount ? `${addedCount}개 추가됨` : "이미 모두 추가됨";
            addAllBtn.setAttribute("disabled", "true");
            DOM.feedSuggestionsStatus.textContent = `${addedCount}개 피드를 추가했습니다. 프로필 설정 저장을 눌러 DB에 반영하세요.`;
        });
    }
    
    DOM.feedSuggestionsList.querySelectorAll(".add-suggested-feed").forEach(btn => {
        btn.addEventListener("click", () => {
            const item = suggestions[Number(btn.dataset.index)];
            if (!item) return;
            if (addSuggestedFeed(item)) {
                btn.textContent = "추가됨";
                btn.setAttribute("disabled", "true");
                DOM.feedSuggestionsStatus.textContent = "피드를 추가했습니다. 프로필 설정 저장을 눌러 DB에 반영하세요.";
            } else {
                btn.textContent = "이미 있음";
                btn.setAttribute("disabled", "true");
            }
        });
    });
}

function renderFeedSuggestionCard(item, idx) {
    const validation = item.validation || {};
    const status = validation.status || "warning";
    const kind = validation.kind || "unknown";
    const canAdd = status === "verified";
    const statusLabel = status === "verified" ? "검증됨" : status === "warning" ? "주의" : "실패";
    const kindLabel = kind === "rss" ? "RSS/Atom" : kind === "docs" ? "Docs/Page" : "Unknown";
    
    return `
        <div class="feed-suggestion-card status-${escapeHtml(status)}">
            <div class="feed-suggestion-main">
                <div class="feed-suggestion-title">
                    <strong>${escapeHtml(item.name || "")}</strong>
                    <span class="suggestion-folder">${escapeHtml(item.category || "other")}</span>
                    <span class="validation-pill ${escapeHtml(status)}">${statusLabel}</span>
                    <span class="validation-pill muted">${kindLabel}</span>
                </div>
                <a href="${escapeHtml(item.url || "")}" target="_blank" class="suggested-url">${escapeHtml(item.url || "")}</a>
                <p>${escapeHtml(item.reason || "경쟁사/제품 모니터링 후보로 추천됩니다.")}</p>
                <small>${escapeHtml(validation.message || "")}</small>
            </div>
            <button type="button" class="btn tiny add-suggested-feed" data-index="${idx}" ${canAdd ? "" : "disabled"}>${canAdd ? "추가" : "검증 실패"}</button>
        </div>
    `;
}

function addSuggestedFeed(item) {
    if (!item || !item.name || !item.url) return false;
    const normalizedUrl = String(item.url).trim().replace(/\/$/, "").toLowerCase();
    const existing = getCurrentFeedPayload().map(feed => String(feed.feed_url).trim().replace(/\/$/, "").toLowerCase());
    if (existing.includes(normalizedUrl)) return false;
    addFeedRow(item.name, item.url);
    return true;
}

function removeKeywordTagAndEmptyGroup(tag) {
    if (!tag) return;
    const folderGroup = tag.closest(".folder-group");
    tag.remove();
    if (folderGroup && folderGroup.querySelectorAll(".keyword-tag").length === 0) {
        folderGroup.remove();
    }
}

function addFeedRowElement(name, url) {
    const row = document.createElement("tr");
    row.innerHTML = `
        <td>${escapeHtml(name)}</td>
        <td><a href="${escapeHtml(url)}" target="_blank" class="card-link-btn">${escapeHtml(url)}</a></td>
        <td class="actions-col">
            <button class="trash-btn remove-feed-row" title="삭제">🗑️</button>
        </td>
    `;
    
    row.querySelector(".remove-feed-row").addEventListener("click", () => {
        row.remove();
    });
    
    DOM.feedRowsContainer.appendChild(row);
}

function addFeedRow(name, url) {
    if (!name || !url) return;
    addFeedRowElement(name, url);
}

async function handleSaveSettings() {
    const profile = profiles.find(p => p.id === currentProfileId);
    if (!profile) return;
    
    const name = profile.name; // Keep profile name for simplicity or we could allow editing
    const apiKey = DOM.apiKeyInput.value.trim();
    const webhook = DOM.webhookInput.value.trim();
    const interval = parseInt(DOM.intervalInput.value) || 6;
    
    // Extract keywords
    const keywords = Array.from(DOM.keywordTagsContainer.querySelectorAll(".keyword-tag"))
                          .map(t => ({
                              keyword: t.getAttribute("data-keyword"),
                              folder: t.getAttribute("data-folder") || "미분류"
                          }));
                          
    // Extract feeds
    const feeds = [];
    const rows = DOM.feedRowsContainer.querySelectorAll("tr");
    rows.forEach(row => {
        const cols = row.querySelectorAll("td");
        if (cols.length >= 2) {
            feeds.push({
                name: cols[0].textContent.trim(),
                feed_url: cols[1].textContent.trim()
            });
        }
    });
    
    const payload = {
        name,
        gemini_api_key: apiKey,
        discord_webhook_url: webhook,
        check_interval_hours: interval,
        keywords,
        feeds,
        report_template_type: DOM.templateTypeSelect.value,
        custom_report_template: DOM.customTemplateInput.value.trim(),
        auto_report_enabled: DOM.autoReportToggle ? DOM.autoReportToggle.checked : true
    };
    
    try {
        const headers = { "Content-Type": "application/json" };
        if (adminPasscode) headers["X-Admin-Passcode"] = adminPasscode;
        
        const res = await fetch(`/api/profiles/${currentProfileId}`, {
            method: "PUT",
            headers,
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            alert("설정이 성공적으로 저장되었습니다!");
            // Refresh profiles state
            await loadProfiles();
        } else {
            const err = await res.json();
            alert(`설정 저장 실패: ${err.detail}`);
        }
    } catch (e) {
        alert("설정 저장 중 오류가 발생했습니다.");
    }
}
async function loadFeeds() {
    if (!currentProfileId) return;
    
    const search = DOM.feedSearch.value.trim();
    const activeFilter = document.querySelector("#feed-tab .filter-btn.active").getAttribute("data-filter");
    
    // Manage folder filter visibility and state
    const profile = profiles.find(p => p.id === currentProfileId);
    if (activeFilter !== "trends") {
        currentFeedFolder = "all";
        if (DOM.feedFolderFilters) DOM.feedFolderFilters.style.display = "none";
    } else {
        const uniqueFolders = profile ? Array.from(new Set(profile.keywords.map(k => k.folder || "미분류").filter(Boolean))) : [];
        updateFolderChips(DOM.feedFolderChips, DOM.feedFolderFilters, uniqueFolders, currentFeedFolder, (folder) => {
            currentFeedFolder = folder;
            loadFeeds();
        });
    }

    try {
        // Fetch docs and trends
        let docs = [];
        let trends = [];
        
        let queryParams = `profile_id=${currentProfileId}&search=${encodeURIComponent(search)}`;
        
        if (activeFilter === "all" || activeFilter === "docs") {
            const res = await fetch(`/api/docs?${queryParams}`);
            docs = await res.json();
        }
        
        if (activeFilter === "all" || activeFilter === "trends") {
            const res = await fetch(`/api/trends?${queryParams}`);
            trends = await res.json();
            
            // Client-side filter by folder if active
            if (currentFeedFolder !== "all") {
                trends = trends.filter(t => (t.folder || "미분류") === currentFeedFolder);
            }
        }
        
        // Merge & sort feeds by source publish date first, then collection date.
        let items = [];
        docs.forEach(d => items.push({ ...d, type: 'doc' }));
        trends.forEach(t => items.push({ ...t, type: 'trend' }));
        
        items.sort((a, b) => getFeedSortTime(b) - getFeedSortTime(a));
        
        // Render
        DOM.feedItemsGrid.innerHTML = "";
        
        if (items.length === 0) {
            DOM.feedEmpty.style.display = "block";
            return;
        }
        
        DOM.feedEmpty.style.display = "none";
        
        const groupByFolder = activeFilter === "trends" && DOM.feedGroupByFolder && DOM.feedGroupByFolder.checked;
        
        if (groupByFolder) {
            // Group items by folder
            const groups = {};
            items.forEach(item => {
                const folder = item.folder || "미분류";
                if (!groups[folder]) {
                    groups[folder] = [];
                }
                groups[folder].push(item);
            });
            
            // Sort folder names alphabetically, but put "미분류" at the very end
            const folderNames = Object.keys(groups).sort((a, b) => {
                if (a === "미분류") return 1;
                if (b === "미분류") return -1;
                return a.localeCompare(b);
            });
            
            folderNames.forEach(folderName => {
                const groupItems = groups[folderName];
                
                // Render folder header
                const header = document.createElement("div");
                header.className = "feed-group-section-header";
                header.innerHTML = `
                    <span class="folder-icon">📁</span>
                    <span>${escapeHtml(folderName)}</span>
                    <span class="folder-count">(${groupItems.length})</span>
                `;
                DOM.feedItemsGrid.appendChild(header);
                
                // Render items inside the folder group
                groupItems.forEach(item => {
                    const card = createFeedCard(item, "feed");
                    DOM.feedItemsGrid.appendChild(card);
                });
            });
        } else {
            // Normal flat chronological rendering
            items.forEach(item => {
                const card = createFeedCard(item, "feed");
                DOM.feedItemsGrid.appendChild(card);
            });
        }
 
        // Bind star toggle handlers
        const starBtns = DOM.feedItemsGrid.querySelectorAll(".feed-star-btn");
        starBtns.forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                const itemId = btn.getAttribute("data-id");
                const itemType = btn.getAttribute("data-type");
                const isCurrentlyStarred = btn.classList.contains("active");
                const nextStarredState = !isCurrentlyStarred;
                
                try {
                    const endpoint = itemType === "doc" ? `/api/docs/${itemId}/star` : `/api/trends/${itemId}/star`;
                    const res = await fetch(`${endpoint}?is_starred=${nextStarredState}`, { method: "PUT" });
                    
                    if (res.ok) {
                        btn.classList.toggle("active", nextStarredState);
                    } else {
                        alert("중요 표시 변경에 실패했습니다.");
                    }
                } catch (err) {
                    console.error("Star toggle error:", err);
                }
            });
        });
    } catch (e) {
        console.error("Failed to load feed items:", e);
    }
}

// --- Starred Feeds Data Loader ---
async function loadStarredFeeds() {
    if (!currentProfileId) return;
    
    const search = DOM.starredSearch.value.trim();
    const activeFilter = document.querySelector("#starred-tab .filter-btn.active").getAttribute("data-filter");
    
    // Manage folder filter visibility and state
    const profile = profiles.find(p => p.id === currentProfileId);
    if (activeFilter !== "trends") {
        currentStarredFolder = "all";
        if (DOM.starredFolderFilters) DOM.starredFolderFilters.style.display = "none";
    } else {
        const uniqueFolders = profile ? Array.from(new Set(profile.keywords.map(k => k.folder || "미분류").filter(Boolean))) : [];
        updateFolderChips(DOM.starredFolderChips, DOM.starredFolderFilters, uniqueFolders, currentStarredFolder, (folder) => {
            currentStarredFolder = folder;
            loadStarredFeeds();
        });
        if (DOM.starredFolderFilters) DOM.starredFolderFilters.style.display = "flex";
    }

    try {
        let docs = [];
        let trends = [];
        
        let queryParams = `profile_id=${currentProfileId}&search=${encodeURIComponent(search)}&starred_only=true`;
        
        if (activeFilter === "all" || activeFilter === "docs") {
            const res = await fetch(`/api/docs?${queryParams}`);
            docs = await res.json();
        }
        
        if (activeFilter === "all" || activeFilter === "trends") {
            const res = await fetch(`/api/trends?${queryParams}`);
            trends = await res.json();
            
            // Client-side filter by folder if active
            if (currentStarredFolder !== "all") {
                trends = trends.filter(t => (t.folder || "미분류") === currentStarredFolder);
            }
        }
        
        // Merge & sort feeds by source publish date first, then collection date.
        let items = [];
        docs.forEach(d => items.push({ ...d, type: 'doc' }));
        trends.forEach(t => items.push({ ...t, type: 'trend' }));
        
        items.sort((a, b) => getFeedSortTime(b) - getFeedSortTime(a));
        
        DOM.starredItemsGrid.innerHTML = "";
        
        if (items.length === 0) {
            DOM.starredEmpty.style.display = "block";
            return;
        }
        
        DOM.starredEmpty.style.display = "none";
        
        const groupByFolder = activeFilter === "trends" && DOM.starredGroupByFolder && DOM.starredGroupByFolder.checked;
        
        if (groupByFolder) {
            // Group items by folder
            const groups = {};
            items.forEach(item => {
                const folder = item.folder || "미분류";
                if (!groups[folder]) {
                    groups[folder] = [];
                }
                groups[folder].push(item);
            });
            
            // Sort folder names alphabetically, but put "미분류" at the very end
            const folderNames = Object.keys(groups).sort((a, b) => {
                if (a === "미분류") return 1;
                if (b === "미분류") return -1;
                return a.localeCompare(b);
            });
            
            folderNames.forEach(folderName => {
                const groupItems = groups[folderName];
                
                // Render folder header
                const header = document.createElement("div");
                header.className = "feed-group-section-header";
                header.innerHTML = `
                    <span class="folder-icon">📁</span>
                    <span>${escapeHtml(folderName)}</span>
                    <span class="folder-count">(${groupItems.length})</span>
                `;
                DOM.starredItemsGrid.appendChild(header);
                
                // Render items inside the folder group
                groupItems.forEach(item => {
                    const card = createFeedCard(item, "starred");
                    DOM.starredItemsGrid.appendChild(card);
                });
            });
        } else {
            // Normal flat chronological rendering
            items.forEach(item => {
                const card = createFeedCard(item, "starred");
                DOM.starredItemsGrid.appendChild(card);
            });
        }
 
        // Bind star toggle handlers for starred tab
        const starBtns = DOM.starredItemsGrid.querySelectorAll(".feed-star-btn");
        starBtns.forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                const itemId = btn.getAttribute("data-id");
                const itemType = btn.getAttribute("data-type");
                
                try {
                    const endpoint = itemType === "doc" ? `/api/docs/${itemId}/star` : `/api/trends/${itemId}/star`;
                    const res = await fetch(`${endpoint}?is_starred=false`, { method: "PUT" });
                    
                    if (res.ok) {
                        // Re-load starred feeds to refresh counts, grouping and display
                        await loadStarredFeeds();
                    } else {
                        alert("중요 표시 변경에 실패했습니다.");
                    }
                } catch (err) {
                    console.error("Star toggle error:", err);
                }
            });
        });
    } catch (e) {
        console.error("Failed to load starred feeds:", e);
    }
}

// --- Compile Report from Starred Items ---
async function handleCompileStarredReport() {
    if (!currentProfileId) return;
    
    const starredCards = DOM.starredItemsGrid.querySelectorAll(".feed-card");
    if (starredCards.length === 0) {
        alert("중요 보관함에 최소 1개 이상의 아이템이 있어야 보고서를 생성할 수 있습니다.");
        return;
    }
    
    if (!confirm("중요 보관함에 있는 아이템들만 분석하여 전략 보고서를 작성하시겠습니까?\n이 작업은 백그라운드에서 진행되며 완료 후 보고서 목록에 등록됩니다.")) {
        return;
    }
    
    try {
        const res = await fetch(`/api/report/generate?profile_id=${currentProfileId}&starred_only=true`, { method: "POST" });
        if (res.ok) {
            alert("중요 보관함 기반 전략 보고서 작성이 시작되었습니다. 시스템 로그 탭으로 이동합니다.");
            // Switch navigation tab to logs
            const logsTab = Array.from(DOM.navItems).find(nav => nav.getAttribute("data-tab") === "logs");
            if (logsTab) logsTab.click();
        } else {
            const err = await res.json();
            alert(`실행 실패: ${err.detail}`);
        }
    } catch (e) {
        alert("서버 연결 실패.");
    }
}

async function handleGenerateReport(reportType) {
    if (!currentProfileId) return;
    const label = reportType === "monthly" ? "월간" : "주간";
    const scopeFolder = selectedReportFolders.join(",");
    const pendingKeyword = DOM.reportScopeKeyword ? DOM.reportScopeKeyword.value.trim() : "";
    const keywordList = Array.from(new Set([...selectedReportKeywords, ...(pendingKeyword ? [pendingKeyword] : [])]));
    const scopeKeyword = keywordList.join(",");
    const matchMode = DOM.reportKeywordMatchMode ? DOM.reportKeywordMatchMode.value : "any";
    const scopeText = scopeFolder || scopeKeyword ? `\n\n분석 범위: ${[scopeFolder && `폴더=${selectedReportFolders.join(" + ")}`, scopeKeyword && `키워드=${keywordList.join(" + ")} (${matchMode === "all" ? "모두 포함" : "하나라도 포함"})`].filter(Boolean).join(", ")}` : "";
    
    if (!confirm(`${label} 기술 신호 및 경쟁사 동향 보고서를 지금 생성하시겠습니까?${scopeText}\n\n생성된 보고서는 보고서 목록에 아카이빙되고 Discord 알림이 전송됩니다.`)) {
        return;
    }
    
    try {
        const params = new URLSearchParams({
            profile_id: currentProfileId,
            report_type: reportType
        });
        if (scopeFolder) params.set("scope_folder", scopeFolder);
        if (scopeKeyword) params.set("scope_keyword", scopeKeyword);
        if (scopeKeyword) params.set("keyword_match_mode", matchMode);
        const res = await fetch(`/api/report/generate?${params.toString()}`, { method: "POST" });
        if (res.ok) {
            alert(`${label} 보고서 생성이 시작되었습니다. 완료 후 보고서 목록에 자동 등록됩니다.`);
            const logsTab = Array.from(DOM.navItems).find(nav => nav.getAttribute("data-tab") === "logs");
            if (logsTab) logsTab.click();
        } else {
            const err = await res.json();
            alert(`실행 실패: ${err.detail}`);
        }
    } catch (e) {
        alert("서버 연결 실패.");
    }
}

function addReportKeyword(keyword) {
    if (!keyword || selectedReportKeywords.includes(keyword)) return;
    selectedReportKeywords.push(keyword);
    renderReportKeywordChips();
}

function renderReportKeywordChips() {
    if (!DOM.reportScopeKeywordChips) return;
    DOM.reportScopeKeywordChips.innerHTML = "";
    selectedReportKeywords.forEach(keyword => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "scope-keyword-chip";
        chip.innerHTML = `${escapeHtml(keyword)} <span aria-hidden="true">&times;</span>`;
        chip.addEventListener("click", () => {
            selectedReportKeywords = selectedReportKeywords.filter(k => k !== keyword);
            renderReportKeywordChips();
        });
        DOM.reportScopeKeywordChips.appendChild(chip);
    });
}

function populateReportScopeFolders(profile) {
    if (!DOM.reportScopeFolderChips || !profile) return;
    const current = new Set(selectedReportFolders);
    DOM.reportScopeFolderChips.innerHTML = "";
    
    const allChip = document.createElement("button");
    allChip.type = "button";
    allChip.className = `scope-folder-chip${selectedReportFolders.length === 0 ? " active" : ""}`;
    allChip.dataset.folder = "";
    allChip.textContent = "전체 폴더";
    allChip.addEventListener("click", () => {
        selectedReportFolders = [];
        populateReportScopeFolders(profile);
    });
    DOM.reportScopeFolderChips.appendChild(allChip);
    
    const folders = Array.from(new Set((profile.keywords || []).map(k => k.folder || "미분류").filter(Boolean)));
    folders.sort((a, b) => {
        if (a === "미분류") return 1;
        if (b === "미분류") return -1;
        return a.localeCompare(b, "ko");
    });
    folders.forEach(folder => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = `scope-folder-chip${current.has(folder) ? " active" : ""}`;
        chip.dataset.folder = folder;
        chip.textContent = folder;
        chip.addEventListener("click", () => {
            if (selectedReportFolders.includes(folder)) {
                selectedReportFolders = selectedReportFolders.filter(f => f !== folder);
            } else {
                selectedReportFolders.push(folder);
            }
            populateReportScopeFolders(profile);
        });
        DOM.reportScopeFolderChips.appendChild(chip);
    });
}

// --- Reports Data Loader ---
async function loadReports() {
    if (!currentProfileId) return;
    
    try {
        const res = await fetch(`/api/reports?profile_id=${currentProfileId}&report_type=${currentReportFilter}`);
        const reports = await res.json();
        
        DOM.reportsListItems.innerHTML = "";
        
        if (reports.length === 0) {
            DOM.reportViewerEmpty.style.display = "flex";
            DOM.reportViewerContent.style.display = "none";
            DOM.reportsListItems.innerHTML = `<div style="font-size:12px; color:var(--text-help); text-align:center; padding:20px;">생성된 보고서가 없습니다.</div>`;
            return;
        }
        
        reports.forEach(rep => {
            const item = document.createElement("div");
            item.className = "report-item";
            const typeLabel = getReportTypeLabel(rep.report_type);
            item.innerHTML = `
                <div class="report-item-kind">${typeLabel}</div>
                <div class="report-item-title">${escapeHtml(rep.title)}</div>
                <div class="report-item-date">${formatDate(rep.created_at)}</div>
            `;
            
            item.addEventListener("click", () => {
                // Remove active classes
                document.querySelectorAll(".report-item").forEach(r => r.classList.remove("active"));
                item.classList.add("active");
                loadReportDetail(rep.id);
            });
            
            DOM.reportsListItems.appendChild(item);
        });
    } catch (e) {
        console.error("Failed to load reports:", e);
    }
}

function getReportTypeLabel(reportType) {
    if (reportType === "monthly") return "월간";
    if (reportType === "starred") return "중요";
    return "주간";
}

async function loadReportDetail(reportId) {
    try {
        const res = await fetch(`/api/reports/${reportId}`);
        const report = await res.json();
        
        currentActiveReport = report; // cache active report
        
        DOM.reportTitleDisplay.textContent = report.title;
        DOM.reportDateDisplay.textContent = formatDate(report.created_at);
        
        // Parse markdown formatting to clean HTML
        DOM.reportBodyDisplay.innerHTML = parseMarkdown(report.content);
        
        DOM.reportViewerEmpty.style.display = "none";
        DOM.reportViewerContent.style.display = "block";
    } catch (e) {
        console.error("Failed to load report detail:", e);
    }
}

// --- Background Task Manager ---
async function triggerBackgroundRun(endpoint) {
    let url = endpoint;
    if (endpoint === "/api/scan") {
        url += `?profile_id=${currentProfileId}`;
    }
    
    try {
        const res = await fetch(url, { method: "POST" });
        if (res.ok) {
            alert("백그라운드 프로세스가 시작되었습니다. 로그 탭을 확인해 주세요.");
            // Switch navigation tab to logs automatically!
            const logsTab = Array.from(DOM.navItems).find(nav => nav.getAttribute("data-tab") === "logs");
            if (logsTab) logsTab.click();
        } else {
            const err = await res.json();
            alert(`실행 실패: ${err.detail}`);
        }
    } catch (e) {
        alert("서버 연결 실패.");
    }
}

async function stopBackgroundRun() {
    if (!confirm("정말로 진행 중인 스캔/분석 프로세스를 강제 중단하시겠습니까?")) return;
    
    try {
        const res = await fetch("/api/stop", { method: "POST" });
        if (res.ok) {
            alert("중단 신호가 전송되었습니다.");
        } else {
            alert("중단 요청에 실패했습니다.");
        }
    } catch (e) {
        alert("서버 연결 실패.");
    }
}

// --- Live Log Polling ---
function startLogPolling() {
    if (isPollingLogs) return;
    isPollingLogs = true;
    
    pollLogsLoop();
}

async function pollLogsLoop() {
    try {
        const res = await fetch("/api/status");
        if (res.ok) {
            const data = await res.json();
            
            // 1. Update UI Status Controls
            if (data.status === "running") {
                updateRunStatus("running", "에이전트가 동작 중입니다...");
                
                DOM.startScanBtn.setAttribute("disabled", "true");
                DOM.startScanBtn.classList.add("disabled");
                DOM.startReportBtn.setAttribute("disabled", "true");
                DOM.startReportBtn.classList.add("disabled");
                DOM.stopProcessBtn.removeAttribute("disabled");
                DOM.stopProcessBtn.classList.remove("disabled");
            } else {
                updateRunStatus("idle", "대기 중 (Idle)");
                
                DOM.startScanBtn.removeAttribute("disabled");
                DOM.startScanBtn.classList.remove("disabled");
                DOM.startReportBtn.removeAttribute("disabled");
                DOM.startReportBtn.classList.remove("disabled");
                DOM.stopProcessBtn.setAttribute("disabled", "true");
                DOM.stopProcessBtn.classList.add("disabled");
            }
            
            // 2. Stream logs
            if (data.logs) {
                // Check if scroll is near bottom before update
                const terminal = DOM.terminalOutputBody;
                const wasAtBottom = terminal.scrollHeight - terminal.clientHeight <= terminal.scrollTop + 50;
                
                // Set logs content
                terminal.innerHTML = escapeHtml(data.logs);
                
                // Keep scroll at bottom if it was already there
                if (wasAtBottom || data.status === "running") {
                    terminal.scrollTop = terminal.scrollHeight;
                }
            }
        }
    } catch (e) {
        console.error("Log poll connection failed:", e);
    }
    
    // Loop
    logPollTimer = setTimeout(pollLogsLoop, 1000);
}

function updateRunStatus(status, label) {
    DOM.statusTexts.forEach(el => {
        el.textContent = label;
        el.className = `status-badge ${status} js-status-text`;
    });
    
    DOM.statusDots.forEach(el => {
        el.className = `status-dot-pulse ${status} js-status-dot`;
    });
}

// --- Bulletin Board Functions ---

async function loadBoardPosts() {
    try {
        const res = await fetch("/api/board");
        const posts = await res.json();
        
        DOM.boardPostsContainer.innerHTML = "";
        
        if (posts.length === 0) {
            DOM.boardPostsContainer.innerHTML = `<div style="text-align:center; color:var(--text-help); padding:40px; font-size:13px;">등록된 의견이 없습니다. 첫 의견을 작성해 보세요!</div>`;
            return;
        }
        
        posts.forEach(post => {
            const card = document.createElement("div");
            card.className = "board-post-card";
            
            // Show trash bin delete button if user is Admin
            const deleteBtn = isAdmin ? `<button class="trash-btn delete-board-post" data-id="${post.id}" title="의견 삭제">🗑️</button>` : "";
            
            card.innerHTML = `
                <div class="board-post-header">
                    <h4 class="board-post-title">${escapeHtml(post.title)}</h4>
                    ${deleteBtn}
                </div>
                <p class="board-post-content">${escapeHtml(post.content)}</p>
                <div class="board-post-meta">
                    <span class="board-post-author">✍️ ${escapeHtml(post.author)}</span>
                    <span class="board-post-date">📅 ${formatDate(post.created_at)}</span>
                </div>
            `;
            
            if (isAdmin) {
                card.querySelector(".delete-board-post").addEventListener("click", () => {
                    handleDeleteBoardPost(post.id);
                });
            }
            
            DOM.boardPostsContainer.appendChild(card);
        });
    } catch (e) {
        console.error("Failed to load board posts:", e);
    }
}

async function handleCreateBoardPost() {
    if (!currentProfileId) {
        alert("선택된 프로필이 없습니다.");
        return;
    }
    
    const title = DOM.boardTitleInput.value.trim();
    const content = DOM.boardContentInput.value.trim();
    
    if (!title || !content) {
        alert("제목과 내용을 모두 기재해 주세요.");
        return;
    }
    
    const payload = {
        profile_id: currentProfileId,
        title: title,
        content: content
    };
    
    try {
        const res = await fetch("/api/board", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            DOM.boardTitleInput.value = "";
            DOM.boardContentInput.value = "";
            await loadBoardPosts();
            alert("의견이 성공적으로 등록되었습니다.");
        } else {
            const err = await res.json();
            alert(`등록 실패: ${err.detail}`);
        }
    } catch (e) {
        alert("의견 등록 오류.");
    }
}

async function handleDeleteBoardPost(postId) {
    if (!confirm("정말로 이 의견 게시글을 삭제하시겠습니까?")) return;
    
    try {
        const headers = {};
        if (adminPasscode) headers["X-Admin-Passcode"] = adminPasscode;
        
        const res = await fetch(`/api/board/${postId}`, {
            method: "DELETE",
            headers
        });
        
        if (res.ok) {
            await loadBoardPosts();
            alert("글이 성공적으로 삭제되었습니다.");
        } else {
            const err = await res.json();
            alert(`삭제 실패: ${err.detail}`);
        }
    } catch (e) {
        alert("삭제 처리 중 오류.");
    }
}

// --- Utilities ---

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;")
              .replace(/"/g, "&quot;")
              .replace(/'/g, "&#039;");
}

function getPublishedDate(item) {
    return item.published_at || item.date || "";
}

function getFeedSortTime(item) {
    const preferredDate = getPublishedDate(item) || item.created_at;
    const parsed = parseDateValue(preferredDate);
    if (!isNaN(parsed.getTime())) return parsed.getTime();
    const fallback = parseDateValue(item.created_at || "");
    return isNaN(fallback.getTime()) ? 0 : fallback.getTime();
}

function parseDateValue(dateStr) {
    if (!dateStr) return new Date(NaN);
    const raw = String(dateStr).trim();
    const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(raw)
        ? raw.replace(" ", "T")
        : raw;
    return new Date(normalized);
}

function formatDateOnly(dateStr) {
    if (!dateStr) return "";
    try {
        const d = parseDateValue(dateStr);
        if (isNaN(d.getTime())) return dateStr;
        return d.toLocaleDateString("ko-KR", {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        });
    } catch (e) {
        return dateStr;
    }
}

function formatDate(dateStr) {
    if (!dateStr) return "";
    // Clean string like "2026-06-01 10:30:00" to "2026-06-01 10:30"
    try {
        const d = new Date(dateStr.replace(" ", "T")); // convert to standard iso format
        if (isNaN(d.getTime())) return dateStr;
        return d.toLocaleDateString("ko-KR", {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
    } catch (e) {
        return dateStr;
    }
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Simple Markdown Parser to render reports beautifully
function parseMarkdown(md) {
    if (!md) return "";
    
    let html = escapeHtml(md);
    
    // Parse Headers: # Title, ## Header
    html = html.replace(/^# (.*?)$/gm, '<h1>$1</h1>');
    html = html.replace(/^## (.*?)$/gm, '<h2>$1</h2>');
    html = html.replace(/^### (.*?)$/gm, '<h3>$1</h3>');
    
    // Parse Bold: **text**
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Parse Lists: - item or * item
    // We do a simple block-based parse or line replacement
    const lines = html.split('\n');
    let inList = false;
    
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();
        if (line.startsWith('- ') || line.startsWith('* ')) {
            if (!inList) {
                lines[i] = '<ul><li>' + line.substring(2) + '</li>';
                inList = true;
            } else {
                lines[i] = '<li>' + line.substring(2) + '</li>';
            }
        } else {
            if (inList) {
                lines[i] = '</ul>' + lines[i];
                inList = false;
            }
        }
    }
    
    if (inList) {
        lines.push('</ul>');
    }
    
    html = lines.join('\n');
    
    // Wrap paragraph lines (lines not inside h1, h2, h3, ul, li)
    const processedLines = html.split('\n').map(line => {
        const trimmed = line.trim();
        if (!trimmed) return '<div><br></div>';
        if (trimmed.startsWith('<h') || trimmed.startsWith('</h') || 
            trimmed.startsWith('<ul') || trimmed.startsWith('</ul') || 
            trimmed.startsWith('<li') || trimmed.startsWith('</li')) {
            return line;
        }
        return `<p>${line}</p>`;
    });
    
    return processedLines.join('\n');
}

// --- Global Templates Handlers ---

async function loadGlobalTemplates() {
    try {
        const res = await fetch("/api/global_templates");
        if (res.ok) {
            globalTemplates = await res.json();
            
            // Populate select dropdown
            DOM.globalTemplateSelect.innerHTML = "";
            globalTemplates.forEach(t => {
                const opt = document.createElement("option");
                opt.value = t.id;
                opt.textContent = getTemplateDisplayName(t.id);
                DOM.globalTemplateSelect.appendChild(opt);
            });
            
            // Trigger initial change event to load current value
            onGlobalTemplateChanged();
        }
    } catch (e) {
        console.error("Failed to load global templates:", e);
    }
}

function getTemplateDisplayName(id) {
    switch (id) {
        case "basic": return "[기본] 기술 신호 및 경쟁사 동향 보고서";
        case "monthly": return "[월간] 솔루션전략팀 월간 전략 보고서";
        case "detailed": return "[상세] 경쟁사 기능 심층분석보고서";
        default: return id;
    }
}

function onGlobalTemplateChanged() {
    const selectedId = DOM.globalTemplateSelect.value;
    const template = globalTemplates.find(t => t.id === selectedId);
    if (template) {
        DOM.globalTemplateContentInput.value = template.template_content;
    } else {
        DOM.globalTemplateContentInput.value = "";
    }
}

async function handleSaveGlobalTemplate() {
    const selectedId = DOM.globalTemplateSelect.value;
    if (!selectedId) return;
    
    const content = DOM.globalTemplateContentInput.value;
    
    try {
        const headers = { "Content-Type": "application/json" };
        if (adminPasscode) headers["X-Admin-Passcode"] = adminPasscode;
        
        const res = await fetch(`/api/global_templates/${selectedId}`, {
            method: "PUT",
            headers,
            body: JSON.stringify({ template_content: content })
        });
        
        if (res.ok) {
            alert("전역 템플릿이 성공적으로 저장되었습니다.");
            // Update local memory cache
            const tIndex = globalTemplates.findIndex(t => t.id === selectedId);
            if (tIndex !== -1) {
                globalTemplates[tIndex].template_content = content;
            }
        } else {
            const err = await res.json();
            alert(`저장 실패: ${err.detail}`);
        }
    } catch (e) {
        alert("전역 템플릿 저장 중 오류가 발생했습니다.");
    }
}

// --- Download & Exporter Utilities ---

function downloadTextFile(filename, text) {
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

function exportReportToPdf(title) {
    // Select the content to export
    const element = DOM.reportBodyDisplay;
    
    // We clone the report view to apply printable black & white styling dynamically 
    // so that the dark theme background and neon fonts are friendly to printers.
    const clone = element.cloneNode(true);
    
    // Create a temporary container for print layout
    const container = document.createElement("div");
    container.style.padding = "40px";
    container.style.backgroundColor = "#ffffff";
    container.style.color = "#111827"; // Dark text
    container.style.fontFamily = "'Outfit', 'Inter', sans-serif";
    container.style.lineHeight = "1.8";
    
    // Add title header
    const titleEl = document.createElement("h1");
    titleEl.textContent = title;
    titleEl.style.fontSize = "26px";
    titleEl.style.fontWeight = "bold";
    titleEl.style.borderBottom = "2px solid #e5e7eb";
    titleEl.style.paddingBottom = "12px";
    titleEl.style.marginBottom = "24px";
    titleEl.style.color = "#111827";
    container.appendChild(titleEl);
    
    // Add metadata (Date)
    const dateEl = document.createElement("div");
    dateEl.textContent = `출처: Tech Watch Tracker | 생성일: ${DOM.reportDateDisplay.textContent}`;
    dateEl.style.fontSize = "12px";
    dateEl.style.color = "#6b7280";
    dateEl.style.marginBottom = "30px";
    container.appendChild(dateEl);
    
    // Inject report body
    container.appendChild(clone);
    
    // Modify CSS styles inside clone to be print friendly (overriding custom CSS)
    const headers = container.querySelectorAll("h1, h2, h3, h4, h5, h6");
    headers.forEach(h => {
        h.style.color = "#111827";
        h.style.borderBottom = "1px solid #e5e7eb";
        h.style.paddingBottom = "6px";
        h.style.marginTop = "24px";
        h.style.marginBottom = "12px";
    });
    
    const paragraphs = container.querySelectorAll("p, li, span, div");
    paragraphs.forEach(p => {
        p.style.color = "#374151"; // Slightly lighter gray text
        p.style.fontSize = "14px";
    });
    
    const listItems = container.querySelectorAll("li");
    listItems.forEach(li => {
        li.style.listStyleType = "disc";
        li.style.marginLeft = "20px";
        li.style.marginBottom = "8px";
    });

    // Options for html2pdf
    const opt = {
        margin: [15, 15, 15, 15],
        filename: `${title}.pdf`,
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: { scale: 2, useCORS: true, letterRendering: true },
        jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
    };
    
    // Generate PDF
    html2pdf().from(container).set(opt).save();
}

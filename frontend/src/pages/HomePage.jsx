import { useState, useEffect, useRef } from 'react';

export default function HomePage() {
    const [placeholderIndex, setPlaceholderIndex] = useState(0);
    const observerRef = useRef(null);

    const placeholders = [
        '"Find the PDF I downloaded last Tuesday..."',
        '"Show me the presentation Sarah sent via WhatsApp..."',
        '"Where is that recipe I saved in August?"'
    ];

    useEffect(() => {
        const interval = setInterval(() => {
            setPlaceholderIndex((prev) => (prev + 1) % placeholders.length);
        }, 3000);
        return () => clearInterval(interval);
    }, [placeholders.length]);

    useEffect(() => {
        observerRef.current = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                    observerRef.current.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1, rootMargin: "0px 0px -50px 0px" });

        document.querySelectorAll('.reveal-on-scroll').forEach((el) => {
            observerRef.current.observe(el);
        });

        return () => observerRef.current?.disconnect();
    }, []);

    return (
        <main className="w-full flex items-center justify-center min-h-screen">
            <div className="flex flex-col w-full font-body-md text-on-surface bg-[#f4f2ee] overflow-hidden relative">
                
                {/* Background Ambient Glow */}
                <div className="absolute top-0 left-0 w-full h-[800px] bg-gradient-to-b from-primary-container/20 via-transparent to-transparent pointer-events-none z-0"></div>
                <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[600px] rounded-full bg-primary/10 blur-[120px] pointer-events-none z-0"></div>
                <div className="absolute top-[10%] right-[-10%] w-[50%] h-[500px] rounded-full bg-secondary/10 blur-[100px] pointer-events-none z-0"></div>

                {/* 1. Hero Section */}
                <section className="relative z-10 flex flex-col items-center justify-center min-h-[90vh] px-md md:px-margin-desktop pt-[120px] pb-xl text-center">
                    <div className="inline-flex items-center gap-2 px-sm py-1 mb-md bg-surface-container-highest rounded-full shadow-sm border border-outline-variant/30 animate-[fade-in-up_0.6s_ease-out_forwards]">
                        <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
                        <span className="text-caption font-label-md text-on-surface-variant tracking-wider uppercase">Chrono AI Beta 1.0</span>
                    </div>
                    <h1 className="font-display-lg text-display-lg md:text-[72px] md:leading-[80px] font-bold text-on-surface max-w-4xl mb-md animate-[fade-in-up_0.8s_ease-out_forwards] opacity-0" style={{ animationDelay: '0.1s' }}>
                        Remember moments, <br className="hidden md:block" />
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-tertiary">not filenames.</span>
                    </h1>
                    <p className="font-body-lg text-body-lg text-on-surface-variant max-w-2xl mb-lg animate-[fade-in-up_0.8s_ease-out_forwards] opacity-0" style={{ animationDelay: '0.2s' }}>
                        Chrono AI turns your scattered digital activity into an intelligent, searchable memory timeline. Ask for what you need, exactly how you remember it.
                    </p>

                    {/* AI Search Box Mockup */}
                    <div className="w-full max-w-2xl bg-surface-container-lowest rounded-xl shadow-xl p-sm flex items-center gap-sm mb-lg border border-outline-variant/30 animate-[fade-in-up_0.8s_ease-out_forwards] opacity-0 relative group" style={{ animationDelay: '0.3s', transition: 'border-color 0.3s ease, box-shadow 0.3s ease' }}>
                        <span className="material-symbols-outlined text-primary ml-sm">magic_button</span>
                        <div className="flex-1 relative h-6 overflow-hidden">
                            <div className="absolute inset-0 flex flex-col transition-transform duration-500 ease-in-out text-body-md text-on-surface-variant text-left whitespace-nowrap" style={{ transform: `translateY(-${placeholderIndex * 24}px)` }}>
                                {placeholders.map((text, i) => (
                                    <span key={i} className="h-6 flex items-center">{text}</span>
                                ))}
                            </div>
                        </div>
                        <div className="absolute -inset-0.5 bg-gradient-to-r from-primary to-tertiary rounded-xl blur opacity-0 group-hover:opacity-20 transition duration-500 z-[-1]"></div>
                    </div>

                    <div className="flex flex-col sm:flex-row gap-md mt-8 animate-[fade-in-up_0.8s_ease-out_forwards] opacity-0" style={{ animationDelay: '0.4s' }}>
                        <button className="bg-primary text-on-primary font-label-md px-lg py-sm rounded-lg shadow-md hover:shadow-lg transition-all duration-300 transform hover:-translate-y-1 relative">
                            <span className="relative z-10">Try Chrono AI</span>
                        </button>
                        <button className="bg-transparent border border-outline-variant text-on-surface font-label-md px-lg py-sm rounded-lg hover:border-primary hover:text-primary hover:bg-primary/5 transition-all duration-300">
                            See How It Works
                        </button>
                    </div>
                </section>

                {/* 2. Product Preview Mockup */}
                <section className="relative z-10 px-md md:px-margin-desktop py-xl reveal-on-scroll is-visible">
                    <div className="w-full max-w-6xl mx-auto">
                        <div className="bg-surface-container-lowest rounded-2xl shadow-2xl overflow-hidden flex flex-col md:flex-row relative border border-outline-variant/20">
                            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary via-secondary to-tertiary"></div>
                            
                            {/* Sidebar / Timeline */}
                            <div className="w-full md:w-1/3 bg-surface-container-low p-md border-r border-outline-variant/20 hidden md:flex flex-col">
                                <h3 className="font-title-lg text-title-lg text-on-surface mb-md">Timeline</h3>
                                <div className="relative pl-sm before:content-[''] before:absolute before:left-[11px] before:top-2 before:bottom-0 before:w-px before:bg-outline-variant/30 flex-1">
                                    <div className="relative mb-lg">
                                        <div className="absolute left-[-15px] top-1.5 w-2.5 h-2.5 rounded-full bg-primary shadow-[0_0_8px_rgba(46,91,255,0.6)]"></div>
                                        <p className="font-label-md text-caption text-primary mb-xs">TODAY</p>
                                        <div className="bg-surface-container-lowest p-sm rounded-lg shadow-sm border border-outline-variant/20">
                                            <p className="text-body-md text-on-surface">Searching for project files...</p>
                                        </div>
                                    </div>
                                    <div className="relative mb-lg opacity-80">
                                        <div className="absolute left-[-15px] top-1.5 w-2.5 h-2.5 rounded-full bg-outline-variant"></div>
                                        <p className="font-label-md text-caption text-on-surface-variant mb-xs">AUG 2, 2026</p>
                                        <div className="bg-surface-container-lowest p-sm rounded-lg shadow-sm border border-outline-variant/20 flex items-center gap-sm">
                                            <span className="material-symbols-outlined text-secondary text-sm">chat</span>
                                            <p className="text-body-md text-on-surface truncate">WhatsApp with Design Team</p>
                                        </div>
                                    </div>
                                    <div className="relative opacity-60">
                                        <div className="absolute left-[-15px] top-1.5 w-2.5 h-2.5 rounded-full bg-outline-variant"></div>
                                        <p className="font-label-md text-caption text-on-surface-variant mb-xs">AUG 1, 2026</p>
                                        <div className="bg-surface-container-lowest p-sm rounded-lg shadow-sm border border-outline-variant/20 flex items-center gap-sm">
                                            <span className="material-symbols-outlined text-tertiary text-sm">description</span>
                                            <p className="text-body-md text-on-surface truncate">FYP_Final_Report.pdf</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            {/* Main Search Area */}
                            <div className="flex-1 p-md md:p-xl flex flex-col bg-surface-container-lowest">
                                <div className="flex items-center gap-sm mb-xl">
                                    <div className="w-8 h-8 rounded-full bg-primary-container/20 flex items-center justify-center">
                                        <span className="material-symbols-outlined text-primary text-sm">person</span>
                                    </div>
                                    <p className="font-body-lg text-body-lg text-on-surface bg-surface-container p-sm rounded-2xl rounded-tl-sm inline-block border border-outline-variant/20">
                                        Find my project file from Aug 1
                                    </p>
                                </div>
                                <div className="flex items-start gap-sm">
                                    <div className="w-8 h-8 rounded-full bg-secondary-container flex items-center justify-center mt-1">
                                        <span className="material-symbols-outlined text-on-secondary-container text-sm">smart_toy</span>
                                    </div>
                                    <div className="flex-1">
                                        <p className="font-body-md text-body-md text-on-surface-variant mb-md">I found 2 possible matches based on your activity around August 1st.</p>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-sm">
                                            <div className="bg-surface-container p-sm rounded-xl border border-primary/30 shadow-sm hover:shadow-md hover:border-primary transition-all cursor-pointer group">
                                                <div className="flex justify-between items-start mb-sm">
                                                    <span className="material-symbols-outlined text-primary">picture_as_pdf</span>
                                                    <span className="text-caption text-primary font-bold bg-primary-container px-2 py-0.5 rounded text-[10px]">98% MATCH</span>
                                                </div>
                                                <h4 className="font-label-md text-on-surface mb-xs truncate group-hover:text-primary transition-colors">FYP_Final_Report.pdf</h4>
                                                <p className="text-caption text-on-surface-variant flex items-center gap-1">
                                                    <span className="material-symbols-outlined text-[14px]">cloud</span> Google Drive
                                                </p>
                                            </div>
                                            <div className="bg-surface-container p-sm rounded-xl border border-outline-variant/30 shadow-sm hover:shadow-md hover:border-outline-variant transition-all cursor-pointer group">
                                                <div className="flex justify-between items-start mb-sm">
                                                    <span className="material-symbols-outlined text-[#25D366]">chat</span>
                                                    <span className="text-caption text-on-surface-variant bg-surface-container-highest px-2 py-0.5 rounded text-[10px]">74% MATCH</span>
                                                </div>
                                                <h4 className="font-label-md text-on-surface mb-xs truncate group-hover:text-primary transition-colors">Received via WhatsApp</h4>
                                                <p className="text-caption text-on-surface-variant">August 2, 2026 • Design Group</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                {/* 3. Problem Section */}
                <section className="py-xl px-md md:px-margin-desktop bg-[#f4f2ee] relative z-10 reveal-on-scroll border-y border-outline-variant/10">
                    <div className="max-w-4xl mx-auto text-center mb-xl">
                        <h2 className="font-headline-lg text-headline-lg md:text-display-md text-on-surface mb-sm">Your digital life is scattered.</h2>
                        <p className="font-body-lg text-body-lg text-on-surface-variant">Data fragmentation makes finding what you need a memory test. You remember context, not file paths.</p>
                    </div>
                    <div className="flex flex-wrap justify-center gap-md max-w-6xl mx-auto">
                        {/* Gmail */}
                        <div className="w-full sm:w-[280px] bg-surface-container-lowest/80 backdrop-blur-xl p-md rounded-2xl border border-outline-variant/20 shadow-md transform transition-transform hover:-translate-y-2 hover:shadow-lg group">
                            <div className="w-12 h-12 rounded-xl bg-[#EA4335]/10 flex items-center justify-center mb-md group-hover:scale-110 transition-transform">
                                <span className="material-symbols-outlined text-[#EA4335]" style={{ fontVariationSettings: "'FILL' 1" }}>mail</span>
                            </div>
                            <h3 className="font-title-lg text-on-surface mb-xs">Gmail</h3>
                            <p className="text-body-md text-on-surface-variant">Lost in thousands of threads and nested attachments.</p>
                        </div>
                        {/* Drive */}
                        <div className="w-full sm:w-[280px] bg-surface-container-lowest/80 backdrop-blur-xl p-md rounded-2xl border border-outline-variant/20 shadow-md transform transition-transform hover:-translate-y-2 hover:shadow-lg group">
                            <div className="w-12 h-12 rounded-xl bg-[#0F9D58]/10 flex items-center justify-center mb-md group-hover:scale-110 transition-transform">
                                <span className="material-symbols-outlined text-[#0F9D58]" style={{ fontVariationSettings: "'FILL' 1" }}>add_to_drive</span>
                            </div>
                            <h3 className="font-title-lg text-on-surface mb-xs">Google Drive</h3>
                            <p className="text-body-md text-on-surface-variant">Folder structures that made sense a year ago, but not today.</p>
                        </div>
                        {/* WhatsApp */}
                        <div className="w-full sm:w-[280px] bg-surface-container-lowest/80 backdrop-blur-xl p-md rounded-2xl border border-outline-variant/20 shadow-md transform transition-transform hover:-translate-y-2 hover:shadow-lg group">
                            <div className="w-12 h-12 rounded-xl bg-[#25D366]/10 flex items-center justify-center mb-md group-hover:scale-110 transition-transform">
                                <span className="material-symbols-outlined text-[#25D366]" style={{ fontVariationSettings: "'FILL' 1" }}>forum</span>
                            </div>
                            <h3 className="font-title-lg text-on-surface mb-xs">WhatsApp</h3>
                            <p className="text-body-md text-on-surface-variant">Crucial documents buried in endless group chats.</p>
                        </div>
                        {/* Calendar */}
                        <div className="w-full sm:w-[280px] bg-surface-container-lowest/80 backdrop-blur-xl p-md rounded-2xl border border-outline-variant/20 shadow-md transform transition-transform hover:-translate-y-2 hover:shadow-lg group">
                            <div className="w-12 h-12 rounded-xl bg-[#4285F4]/10 flex items-center justify-center mb-md group-hover:scale-110 transition-transform">
                                <span className="material-symbols-outlined text-[#4285F4]" style={{ fontVariationSettings: "'FILL' 1" }}>event</span>
                            </div>
                            <h3 className="font-title-lg text-on-surface mb-xs">Calendar</h3>
                            <p className="text-body-md text-on-surface-variant">Meeting notes detached from the files they reference.</p>
                        </div>
                        {/* File Explorer */}
                        <div className="w-full sm:w-[280px] bg-surface-container-lowest/80 backdrop-blur-xl p-md rounded-2xl border border-outline-variant/20 shadow-md transform transition-transform hover:-translate-y-2 hover:shadow-lg group">
                            <div className="w-12 h-12 rounded-xl bg-[#FFBC00]/10 flex items-center justify-center mb-md group-hover:scale-110 transition-transform">
                                <span className="material-symbols-outlined text-[#FFBC00]" style={{ fontVariationSettings: "'FILL' 1" }}>folder</span>
                            </div>
                            <h3 className="font-title-lg text-on-surface mb-xs">Local Files</h3>
                            <p className="text-body-md text-on-surface-variant">"Final_final_v3.docx" scattered across desktop and downloads.</p>
                        </div>
                    </div>
                </section>

                {/* 4. Solution Flow */}
                <section className="py-xl px-md md:px-margin-desktop bg-surface-container-lowest relative z-10 reveal-on-scroll">
                    <div className="max-w-6xl mx-auto">
                        <h2 className="font-headline-lg text-headline-lg text-center text-on-surface mb-xl">How Chrono AI Works</h2>
                        <div className="flex flex-col md:flex-row items-center justify-between gap-lg relative">
                            <div className="absolute top-1/2 left-[5%] right-[5%] h-0.5 bg-gradient-to-r from-outline-variant/20 via-primary/40 to-outline-variant/20 hidden md:block -translate-y-1/2"></div>
                            
                            <div className="flex flex-col items-center text-center w-full md:w-1/4 relative z-10 group">
                                <div className="w-16 h-16 rounded-2xl bg-surface border border-outline-variant/40 flex items-center justify-center mb-md group-hover:border-primary transition-colors group-hover:shadow-md bg-white">
                                    <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors text-2xl">cable</span>
                                </div>
                                <h4 className="font-label-md text-on-surface mb-xs">1. Connect Sources</h4>
                                <p className="text-caption text-on-surface-variant">Link your apps securely.</p>
                            </div>
                            <div className="flex flex-col items-center text-center w-full md:w-1/4 relative z-10 group">
                                <div className="w-16 h-16 rounded-2xl bg-surface border border-outline-variant/40 flex items-center justify-center mb-md group-hover:border-secondary transition-colors group-hover:shadow-md bg-white">
                                    <span className="material-symbols-outlined text-on-surface-variant group-hover:text-secondary transition-colors text-2xl">psychology</span>
                                </div>
                                <h4 className="font-label-md text-on-surface mb-xs">2. AI Understands</h4>
                                <p className="text-caption text-on-surface-variant">Analyzes context, not just text.</p>
                            </div>
                            <div className="flex flex-col items-center text-center w-full md:w-1/4 relative z-10 group">
                                <div className="w-16 h-16 rounded-2xl bg-surface border border-outline-variant/40 flex items-center justify-center mb-md group-hover:border-tertiary transition-colors group-hover:shadow-md bg-white">
                                    <span className="material-symbols-outlined text-on-surface-variant group-hover:text-tertiary transition-colors text-2xl">linear_scale</span>
                                </div>
                                <h4 className="font-label-md text-on-surface mb-xs">3. Builds Timeline</h4>
                                <p className="text-caption text-on-surface-variant">Creates a unified temporal view.</p>
                            </div>
                            <div className="flex flex-col items-center text-center w-full md:w-1/4 relative z-10 group">
                                <div className="w-16 h-16 rounded-2xl bg-primary-container border border-primary/20 flex items-center justify-center mb-md shadow-md group-hover:shadow-lg transition-shadow">
                                    <span className="material-symbols-outlined text-primary text-2xl text-white">search</span>
                                </div>
                                <h4 className="font-label-md text-on-surface mb-xs">4. Ask Naturally</h4>
                                <p className="text-caption text-on-surface-variant">Find instantly.</p>
                            </div>
                        </div>
                    </div>
                </section>

                {/* 5 & 6. Timeline Showcase & Search Demo */}
                <section className="py-xl px-md md:px-margin-desktop bg-[#f4f2ee] relative z-10 overflow-hidden reveal-on-scroll border-y border-outline-variant/10">
                    <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-xl">
                        {/* Left: Timeline */}
                        <div>
                            <h2 className="font-headline-lg text-headline-lg text-on-surface mb-lg">Your digital life,<br/><span className="text-primary">remembered.</span></h2>
                            <div className="bg-surface-container-lowest p-md rounded-2xl border border-outline-variant/30 shadow-lg relative pl-lg">
                                <div className="absolute left-6 top-6 bottom-6 w-px bg-gradient-to-b from-primary via-tertiary to-transparent"></div>
                                <div className="mb-sm text-label-md font-label-md text-on-surface-variant uppercase tracking-widest pl-md">August 2026</div>
                                
                                <div className="relative pl-md py-sm group">
                                    <div className="absolute left-[-21px] top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-surface-container-lowest border-2 border-primary group-hover:scale-150 group-hover:bg-primary transition-all duration-300 z-10"></div>
                                    <div className="bg-surface-container p-sm rounded-xl border border-outline-variant/20 shadow-sm group-hover:border-primary/50 transition-colors">
                                        <div className="flex justify-between items-start mb-1">
                                            <span className="text-caption font-bold text-on-surface">Aug 2 • 14:30</span>
                                            <span className="material-symbols-outlined text-[#25D366] text-[16px]">chat</span>
                                        </div>
                                        <p className="text-body-md text-on-surface">Received design feedback via WhatsApp</p>
                                    </div>
                                </div>

                                <div className="relative pl-md py-sm group">
                                    <div className="absolute left-[-21px] top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-surface-container-lowest border-2 border-secondary group-hover:scale-150 group-hover:bg-secondary transition-all duration-300 z-10"></div>
                                    <div className="bg-surface-container p-sm rounded-xl border border-outline-variant/20 shadow-sm group-hover:border-secondary/50 transition-colors">
                                        <div className="flex justify-between items-start mb-1">
                                            <span className="text-caption font-bold text-on-surface">Aug 1 • 09:15</span>
                                            <span className="material-symbols-outlined text-[#0F9D58] text-[16px]">add_to_drive</span>
                                        </div>
                                        <p className="text-body-md text-on-surface">Created 'FYP_Final_Report.pdf' in Drive</p>
                                    </div>
                                </div>

                                <div className="relative pl-md py-sm group">
                                    <div className="absolute left-[-21px] top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-surface-container-lowest border-2 border-tertiary group-hover:scale-150 group-hover:bg-tertiary transition-all duration-300 z-10"></div>
                                    <div className="bg-surface-container p-sm rounded-xl border border-outline-variant/20 shadow-sm group-hover:border-tertiary/50 transition-colors">
                                        <div className="flex justify-between items-start mb-1">
                                            <span className="text-caption font-bold text-on-surface">July 28 • 11:00</span>
                                            <span className="material-symbols-outlined text-[#EA4335] text-[16px]">mail</span>
                                        </div>
                                        <p className="text-body-md text-on-surface">Emailed prof about report structure</p>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Right: Detailed Result Card */}
                        <div className="flex flex-col justify-center">
                            <div className="bg-surface-container-lowest p-md rounded-2xl shadow-xl border border-outline-variant/30 transform hover:-translate-y-1 transition-transform duration-500 relative">
                                <div className="absolute -top-4 -right-4 w-24 h-24 bg-primary/10 rounded-full blur-[30px]"></div>
                                <div className="flex items-center gap-sm border-b border-outline-variant/20 pb-sm mb-sm">
                                    <span className="material-symbols-outlined text-primary">auto_awesome</span>
                                    <span className="text-label-md font-label-md text-on-surface">Chrono Search Result</span>
                                </div>
                                <h3 className="font-title-lg text-title-lg text-on-surface mb-xs truncate">FYP_Final_Report.pdf</h3>
                                <div className="grid grid-cols-2 gap-sm mb-md text-body-md">
                                    <div>
                                        <p className="text-caption text-on-surface-variant font-bold">SOURCE</p>
                                        <p className="text-on-surface flex items-center gap-1"><span className="material-symbols-outlined text-[14px]">cloud</span> Google Drive</p>
                                    </div>
                                    <div>
                                        <p className="text-caption text-on-surface-variant font-bold">DATE</p>
                                        <p className="text-on-surface">August 1, 2026</p>
                                    </div>
                                    <div className="col-span-2">
                                        <p className="text-caption text-on-surface-variant font-bold">CONTEXT</p>
                                        <p className="text-on-surface text-sm">Created during 'Project Sync' meeting. Referenced in WhatsApp chat on Aug 2.</p>
                                    </div>
                                </div>
                                <button className="w-full bg-primary text-on-primary font-label-md py-sm rounded-lg flex items-center justify-center gap-sm hover:bg-primary-fixed hover:text-on-primary-fixed transition-colors shadow-md">
                                    Open File <span className="material-symbols-outlined text-[18px]">open_in_new</span>
                                </button>
                            </div>
                        </div>
                    </div>
                </section>

                {/* 7. Connected Sources List */}
                <section className="py-lg px-md md:px-margin-desktop bg-surface-container-lowest text-center reveal-on-scroll is-visible border-b border-outline-variant/10">
                    <div className="max-w-4xl mx-auto">
                        <h3 className="font-title-lg text-on-surface mb-md">Integrates with your workflow</h3>
                        <div className="flex flex-wrap justify-center gap-md items-center">
                            {/* Active Source */}
                            <div className="flex items-center gap-2 bg-surface px-sm py-1.5 rounded-full border border-primary/40 text-on-surface shadow-sm">
                                <span className="material-symbols-outlined text-[#0F9D58] text-[20px]" style={{ fontVariationSettings: "'FILL' 1" }}>add_to_drive</span>
                                <span className="font-label-md text-sm">Google Drive</span>
                                <span className="w-2 h-2 rounded-full bg-primary animate-pulse ml-1"></span>
                            </div>
                            {/* Coming Soon */}
                            <div className="flex items-center gap-2 px-sm py-1.5 rounded-full text-on-surface-variant opacity-60">
                                <span className="material-symbols-outlined text-[20px]">mail</span>
                                <span className="font-label-md text-sm">Gmail</span>
                            </div>
                            <div className="flex items-center gap-2 px-sm py-1.5 rounded-full text-on-surface-variant opacity-60">
                                <span className="material-symbols-outlined text-[20px]">forum</span>
                                <span className="font-label-md text-sm">WhatsApp</span>
                            </div>
                            <div className="flex items-center gap-2 px-sm py-1.5 rounded-full text-on-surface-variant opacity-60">
                                <span className="material-symbols-outlined text-[20px]">event</span>
                                <span className="font-label-md text-sm">Calendar</span>
                            </div>
                            <div className="flex items-center gap-2 px-sm py-1.5 rounded-full text-on-surface-variant opacity-60">
                                <span className="material-symbols-outlined text-[20px]">folder</span>
                                <span className="font-label-md text-sm">Local Files</span>
                            </div>
                        </div>
                        <p className="text-caption text-on-surface-variant mt-sm uppercase tracking-widest font-bold">More sources coming soon</p>
                    </div>
                </section>

                {/* 8. Final CTA */}
                <section className="py-[120px] px-md md:px-margin-desktop bg-[#f4f2ee] relative z-10 flex flex-col items-center justify-center text-center overflow-hidden reveal-on-scroll is-visible">
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
                        <div className="w-[80%] h-[300px] rounded-full bg-primary/10 blur-[100px]"></div>
                    </div>
                    <h2 className="font-display-md text-display-md md:text-display-lg text-on-surface mb-sm relative z-10 max-w-3xl">
                        Stop searching. <br /><span className="text-transparent bg-clip-text bg-gradient-to-r from-secondary to-primary">Start remembering.</span>
                    </h2>
                    <p className="font-body-lg text-body-lg text-on-surface-variant mb-lg relative z-10">Join the beta and reclaim your digital memory.</p>
                    <button className="relative z-10 bg-primary text-on-primary font-label-md px-[40px] py-md rounded-xl shadow-lg hover:shadow-xl hover:bg-primary-fixed hover:text-on-primary-fixed transition-all duration-300 transform hover:-translate-y-1 flex items-center gap-2 text-lg">
                        Try Chrono AI <span className="material-symbols-outlined">arrow_forward</span>
                    </button>
                </section>

                {/* 9. Meet the Team */}
                <section className="py-xl px-md md:px-margin-desktop bg-surface-container-lowest relative z-10 reveal-on-scroll is-visible border-t border-outline-variant/20">
                    <div className="max-w-6xl mx-auto">
                        <div className="text-center mb-xl">
                            <h2 className="font-headline-lg text-headline-lg md:text-display-md text-on-surface mb-sm">Meet the Team</h2>
                            <p className="font-body-lg text-body-lg text-on-surface-variant max-w-2xl mx-auto">The minds behind Chrono AI's intelligent memory timeline.</p>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-lg">
                            {/* Member 1 */}
                            <div className="group bg-surface-container rounded-2xl overflow-hidden border border-outline-variant/30 hover:border-primary/50 hover:shadow-lg transition-all duration-300 bg-white shadow-sm">
<div className="aspect-square overflow-hidden bg-surface">
    <img 
        alt="Abdullah Akram" 
        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" 
        src="/abdullah.jpeg" 
    />
</div>
                                <div className="p-md text-center">
                                    <h3 className="font-title-lg text-on-surface mb-xs">Abdullah Akram</h3>
                                    <p className="text-caption text-primary font-bold">Front End Developer | Android Developer</p>
                                </div>
                            </div>
                            {/* Member 2 */}
                            <div className="group bg-surface-container rounded-2xl overflow-hidden border border-outline-variant/30 hover:border-primary/50 hover:shadow-lg transition-all duration-300 bg-white shadow-sm">
                                <div className="aspect-square overflow-hidden bg-surface">
                                    <img alt="Umer Jahangir" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" src="/umer.jpeg" />
                                </div>
                                <div className="p-md text-center">
                                    <h3 className="font-title-lg text-on-surface mb-xs">Umer Jahangir</h3>
                                    <p className="text-caption text-primary font-bold">Software Engineer | Python Developer | Applied AI Engineer | Computer Vision Engineer</p>
                                </div>
                            </div>
                            {/* Member 3 */}
                            <div className="group bg-surface-container rounded-2xl overflow-hidden border border-outline-variant/30 hover:border-primary/50 hover:shadow-lg transition-all duration-300 bg-white shadow-sm">
                                <div className="aspect-square overflow-hidden bg-surface">
                                    <img alt="Zia Ul Rehman" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"  src="/zia.jpeg"  />
                                </div>
                                <div className="p-md text-center">
                                    <h3 className="font-title-lg text-on-surface mb-xs">Zia Ul Rehman</h3>
                                    <p className="text-caption text-primary font-bold">Software Engineer | AI Automation | Embedded System Developer</p>
                                </div>
                            </div>
                            {/* Member 4 */}
                            <div className="group bg-surface-container rounded-2xl overflow-hidden border border-outline-variant/30 hover:border-primary/50 hover:shadow-lg transition-all duration-300 bg-white shadow-sm">
                                <div className="aspect-square overflow-hidden bg-surface">
                                    <img alt="Talha Ashraf" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" src="/talha.png" />
                                </div>
                                <div className="p-md text-center">
                                    <h3 className="font-title-lg text-on-surface mb-xs">Talha Ashraf</h3>
                                    <p className="text-caption text-primary font-bold">AI Automation | Agents</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Footer */}
                <footer className="bg-surface-container-high pt-xl pb-md px-md md:px-margin-desktop border-t border-outline-variant/30 relative z-10">
                    <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-xl mb-xl">
                        <div className="lg:col-span-2">
                            <div className="flex items-center gap-2 mb-md">
                                <span className="font-headline-lg text-title-lg tracking-tight text-on-surface">Chrono AI</span>
                            </div>
                            <p className="text-body-md text-on-surface-variant mb-lg">
                                Remember moments, not filenames. Chrono AI turns your scattered digital activity into an intelligent, searchable memory timeline.
                            </p>
                            <div className="flex items-center gap-sm">
                                <a className="w-10 h-10 rounded-full bg-surface-container flex items-center justify-center hover:bg-primary/10 hover:text-primary transition-colors text-on-surface-variant border border-outline-variant/30" href="#">
                                    <span className="material-symbols-outlined text-[20px]">public</span>
                                </a>
                                <a className="w-10 h-10 rounded-full bg-surface-container flex items-center justify-center hover:bg-primary/10 hover:text-primary transition-colors text-on-surface-variant border border-outline-variant/30" href="#">
                                    <span className="material-symbols-outlined text-[20px]">share</span>
                                </a>
                                <a className="w-10 h-10 rounded-full bg-surface-container flex items-center justify-center hover:bg-primary/10 hover:text-primary transition-colors text-on-surface-variant border border-outline-variant/30" href="#">
                                    <span className="material-symbols-outlined text-[20px]">mail</span>
                                </a>
                            </div>
                        </div>
                        <div>
                            <h4 className="font-label-md text-on-surface mb-md">Product</h4>
                            <ul className="space-y-sm">
                                <li><a className="text-body-md text-on-surface-variant hover:text-primary transition-colors" href="#">Features</a></li>
                                <li><a className="text-body-md text-on-surface-variant hover:text-primary transition-colors" href="#">Timeline</a></li>
                                <li><a className="text-body-md text-on-surface-variant hover:text-primary transition-colors" href="#">Security</a></li>
                            </ul>
                        </div>
                        <div>
                            <h4 className="font-label-md text-on-surface mb-md">Company</h4>
                            <ul className="space-y-sm">
                                <li><a className="text-body-md text-on-surface-variant hover:text-primary transition-colors" href="#">About</a></li>
                                <li><a className="text-body-md text-on-surface-variant hover:text-primary transition-colors" href="#">Careers</a></li>
                                <li><a className="text-body-md text-on-surface-variant hover:text-primary transition-colors" href="#">Contact</a></li>
                            </ul>
                        </div>
                        <div>
                            <h4 className="font-label-md text-on-surface mb-md">Legal</h4>
                            <ul className="space-y-sm">
                                <li><a className="text-body-md text-on-surface-variant hover:text-primary transition-colors" href="#">Privacy Policy</a></li>
                                <li><a className="text-body-md text-on-surface-variant hover:text-primary transition-colors" href="#">Terms of Service</a></li>
                            </ul>
                        </div>
                    </div>
                    <div className="border-t border-outline-variant/30 pt-md flex flex-col md:flex-row items-center justify-between gap-sm">
                        <p className="text-caption text-on-surface-variant">© 2026 Chrono AI. All rights reserved.</p>
                        <div className="flex gap-md">
                            <a className="text-caption text-on-surface-variant hover:text-primary transition-colors" href="#">Privacy</a>
                            <a className="text-caption text-on-surface-variant hover:text-primary transition-colors" href="#">Terms</a>
                        </div>
                    </div>
                </footer>
            </div>
        </main>
    );
}

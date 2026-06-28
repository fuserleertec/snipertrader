/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from 'react';
import { Factor, AlignmentStatus, ScoreCategory, TradeSetup } from './types';
import { DEFAULT_FACTORS, PRESET_SCENARIOS } from './data/confluenceFactors';
import FactorCard from './components/FactorCard';
import ScoreSummary from './components/ScoreSummary';
import SavedSetups from './components/SavedSetups';
import ScenariosQuickSelector from './components/ScenariosQuickSelector';
import { TrendingUp, Clock, CalendarDays, Compass, HelpCircle, ShieldAlert, BookOpen, Sun, Moon } from 'lucide-react';
import { motion, LayoutGroup } from 'motion/react';

export default function App() {
  // 0. Theme State
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    return (localStorage.getItem('sms_theme') as 'light' | 'dark') || 'dark';
  });

  // 1. Core Calculator State
  const [factors, setFactors] = useState<Factor[]>(() => {
    const saved = localStorage.getItem('sms_current_factors');
    return saved ? JSON.parse(saved) : DEFAULT_FACTORS;
  });

  const [symbol, setSymbol] = useState(() => {
    return localStorage.getItem('sms_current_symbol') || 'EURUSD';
  });

  const [direction, setDirection] = useState<'Long' | 'Short'>(() => {
    return (localStorage.getItem('sms_current_direction') as 'Long' | 'Short') || 'Long';
  });

  const [journalNotes, setJournalNotes] = useState(() => {
    return localStorage.getItem('sms_current_journal') || '';
  });

  const [savedSetups, setSavedSetups] = useState<TradeSetup[]>(() => {
    const saved = localStorage.getItem('sms_saved_setups');
    return saved ? JSON.parse(saved) : [];
  });

  const [activeScenarioName, setActiveScenarioName] = useState<string | null>(null);

  // 2. New York Clock & Session State
  const [nyClock, setNyClock] = useState({
    time: '00:00:00 AM',
    killzone: 'Outside Killzones',
    zoneColor: 'text-slate-500 bg-slate-950/40 border-slate-900',
  });

  // Keep state synchronized with LocalStorage
  useEffect(() => {
    localStorage.setItem('sms_current_factors', JSON.stringify(factors));
  }, [factors]);

  useEffect(() => {
    localStorage.setItem('sms_current_symbol', symbol);
  }, [symbol]);

  useEffect(() => {
    localStorage.setItem('sms_current_direction', direction);
  }, [direction]);

  useEffect(() => {
    localStorage.setItem('sms_current_journal', journalNotes);
  }, [journalNotes]);

  useEffect(() => {
    localStorage.setItem('sms_saved_setups', JSON.stringify(savedSetups));
  }, [savedSetups]);

  // Handle document level theme class
  useEffect(() => {
    localStorage.setItem('sms_theme', theme);
    if (theme === 'light') {
      document.body.classList.add('light-theme');
    } else {
      document.body.classList.remove('light-theme');
    }
  }, [theme]);

  // Handle New York time ticker
  useEffect(() => {
    const updateTime = () => {
      try {
        const timeOptions = {
          timeZone: 'America/New_York',
          hour12: false,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        } as const;

        const formatter = new Intl.DateTimeFormat('en-US', timeOptions);
        const parts = formatter.formatToParts(new Date());

        let hour = 0;
        let minute = 0;

        parts.forEach((part) => {
          if (part.type === 'hour') hour = parseInt(part.value, 10);
          if (part.type === 'minute') minute = parseInt(part.value, 10);
        });

        const formattedTime = new Intl.DateTimeFormat('en-US', {
          timeZone: 'America/New_York',
          hour12: true,
          hour: 'numeric',
          minute: '2-digit',
          second: '2-digit',
        }).format(new Date());

        // ICT Killzones based on NY Time (EST/EDT)
        // Asia Killzone: 20:00 - 00:00 (8 PM - 12 AM)
        // London Killzone: 02:00 - 05:00 (2 AM - 5 AM)
        // NY AM Killzone: 07:00 - 10:00 (7 AM - 10 AM)
        // London Close: 10:00 - 12:00 (10 AM - 12 PM)
        // NY PM Killzone: 13:00 - 16:00 (1 PM - 4 PM)
        let killzone = 'Outside Session';
        let zoneColor = 'text-slate-500 bg-slate-950/40 border-slate-800/80';

        if (hour >= 20 || hour < 0) {
          killzone = 'Asia Killzone';
          zoneColor = 'text-purple-400 bg-purple-950/20 border-purple-900/30';
        } else if (hour >= 2 && hour < 5) {
          killzone = 'London Killzone';
          zoneColor = 'text-sky-400 bg-sky-950/20 border-sky-900/30';
        } else if (hour >= 7 && hour < 10) {
          killzone = 'NY AM Killzone';
          zoneColor = 'text-emerald-400 bg-emerald-950/20 border-emerald-900/30 font-semibold';
        } else if (hour >= 10 && hour < 12) {
          killzone = 'London Close';
          zoneColor = 'text-amber-400 bg-amber-950/20 border-amber-900/30';
        } else if (hour >= 13 && hour < 16) {
          killzone = 'NY PM Killzone';
          zoneColor = 'text-emerald-400 bg-emerald-950/20 border-emerald-900/30 font-semibold';
        }

        setNyClock({
          time: formattedTime,
          killzone,
          zoneColor,
        });
      } catch (err) {
        // Fallback for environment constraints
        setNyClock({
          time: new Date().toLocaleTimeString(),
          killzone: 'System Clock',
          zoneColor: 'text-slate-400 bg-slate-900/40 border-slate-800',
        });
      }
    };

    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  // 3. Mathematical Calculations
  const calculateTotalScore = (): { score: number; category: ScoreCategory } => {
    let actualPoints = 0;
    let totalMaxWeight = 0;

    factors.forEach((f) => {
      totalMaxWeight += f.weight;
      if (f.status === 'Yes') {
        actualPoints += f.weight;
      } else if (f.status === 'Partial') {
        actualPoints += Math.round(f.weight / 2);
      }
    });

    if (totalMaxWeight === 0) return { score: 0, category: 'BELOW_THRESHOLD' };

    const scorePct = Math.round((actualPoints / totalMaxWeight) * 100);

    let category: ScoreCategory = 'BELOW_THRESHOLD';
    if (scorePct >= 90) {
      category = 'ELITE';
    } else if (scorePct >= 80) {
      category = 'PRIME';
    }

    return { score: scorePct, category };
  };

  const { score, category } = calculateTotalScore();

  // Check if current factors match any pre-defined scenario exactly
  useEffect(() => {
    const matchingScenario = PRESET_SCENARIOS.find((scenario) => {
      return factors.every((f) => scenario.factors[f.id as keyof typeof scenario.factors] === f.status);
    });
    setActiveScenarioName(matchingScenario ? matchingScenario.name : null);
  }, [factors]);

  // 4. Input Handlers
  const handleStatusChange = (id: string, status: AlignmentStatus) => {
    setFactors((prev) =>
      prev.map((f) => (f.id === id ? { ...f, status } : f))
    );
  };

  const handleNotesChange = (id: string, notes: string) => {
    setFactors((prev) =>
      prev.map((f) => (f.id === id ? { ...f, notes } : f))
    );
  };

  const handleWeightChange = (id: string, weight: number) => {
    setFactors((prev) =>
      prev.map((f) => (f.id === id ? { ...f, weight } : f))
    );
  };

  const handleSelectScenario = (scenarioFactors: Record<string, AlignmentStatus>) => {
    setFactors((prev) =>
      prev.map((f) => ({
        ...f,
        status: scenarioFactors[f.id] || 'No',
      }))
    );
  };

  const handleResetCalculator = () => {
    setFactors(DEFAULT_FACTORS.map(f => ({ ...f, status: 'No', notes: '' })));
    setSymbol('EURUSD');
    setDirection('Long');
    setJournalNotes('');
    setActiveScenarioName(null);
  };

  // 5. Journal Storage Operations
  const handleSaveSetup = () => {
    if (!symbol.trim()) {
      alert('Please enter a valid asset symbol before logging.');
      return;
    }

    const newSetup: TradeSetup = {
      id: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2, 9),
      timestamp: new Date().toISOString(),
      symbol: symbol.trim().toUpperCase(),
      direction,
      score,
      category,
      factors: factors.map((f) => ({
        id: f.id,
        name: f.name,
        status: f.status,
        notes: f.notes,
      })),
      journalNotes: journalNotes.trim() || undefined,
    };

    setSavedSetups((prev) => [newSetup, ...prev]);
    setJournalNotes('');
    alert(`Successfully logged ${newSetup.symbol} setup with a score of ${newSetup.score}% (${category})!`);
  };

  const handleLoadSetup = (setup: TradeSetup) => {
    setSymbol(setup.symbol);
    setDirection(setup.direction);
    setJournalNotes(setup.journalNotes || '');
    
    // Map status/notes back, keep current weights
    setFactors((prev) =>
      prev.map((f) => {
        const savedFactor = setup.factors.find((sf) => sf.id === f.id);
        return {
          ...f,
          status: savedFactor ? savedFactor.status : 'No',
          notes: savedFactor ? savedFactor.notes : '',
        };
      })
    );
  };

  const handleDeleteSetup = (id: string) => {
    setSavedSetups((prev) => prev.filter((s) => s.id !== id));
  };

  const handleClearAll = () => {
    setSavedSetups([]);
  };

  const handleImportSetups = (imported: TradeSetup[]) => {
    setSavedSetups((prev) => {
      // Avoid duplicate IDs
      const existingIds = new Set(prev.map((s) => s.id));
      const filteredImported = imported.filter((s) => !existingIds.has(s.id));
      return [...filteredImported, ...prev];
    });
  };

  return (
    <div className={`min-h-screen bg-slate-950 text-slate-100 flex flex-col antialiased border-8 border-slate-900 ${theme === 'light' ? 'light-theme' : ''}`}>
      
      {/* 1. Header Section */}
      <header className="bg-slate-900 px-6 sm:px-10 py-5 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-800 sticky top-0 z-50">
        <div>
          <h1 className="text-xs font-bold tracking-[0.3em] text-emerald-500 uppercase">ICT Foundation Masterplan</h1>
          <p className="text-xl sm:text-2xl font-light tracking-tight text-white mt-1">Smart Money Score Calculator <span className="text-slate-500 text-sm font-mono ml-2">v1.1</span></p>
        </div>
        
        <div className="flex items-center gap-5 w-full sm:w-auto justify-between sm:justify-end">
          {/* Light / Dark Mode Toggle */}
          <button
            type="button"
            id="theme-toggle-btn"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="w-10 h-10 rounded-xl border border-slate-800 bg-slate-950/40 hover:bg-slate-950/80 text-slate-400 hover:text-slate-200 transition-all flex items-center justify-center cursor-pointer shrink-0"
            title={theme === 'dark' ? "Switch to Light Version" : "Switch to Dark Version"}
          >
            {theme === 'dark' ? <Sun className="w-4 h-4 text-amber-400 animate-spin-slow" /> : <Moon className="w-4 h-4 text-sky-500" />}
          </button>

          <div className="text-left sm:text-right">
            <p className="text-[10px] uppercase tracking-widest text-slate-500">NY SESSION & CLOCK</p>
            <p className="text-xs font-mono text-slate-300 mt-0.5">{nyClock.killzone} | {nyClock.time}</p>
          </div>
          <div className="w-10 h-10 rounded-full border border-slate-700 flex items-center justify-center bg-slate-800/50 shrink-0">
            <div className={`w-2.5 h-2.5 rounded-full transition-all duration-500 ${
              nyClock.killzone.includes('Killzone')
                ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)]'
                : 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]'
            }`} />
          </div>
        </div>
      </header>

      {/* 2. Main Work Stage */}
      <main className="grow max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
        
        {/* Scenario Templates Selector */}
        <ScenariosQuickSelector
          onSelectScenario={handleSelectScenario}
          activeScenarioName={activeScenarioName}
        />

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* LEFT: Factor Cards & Evaluation Checklist (Grid Column 7) */}
          <section className="lg:col-span-7 space-y-5">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <h2 className="text-base font-bold text-slate-200 tracking-tight font-sans">
                  Confluence Evaluation Suite
                </h2>
                <p className="text-xs text-slate-400 font-sans">
                  Score each of the 5 factors according to live orderflow details.
                </p>
              </div>
              <button
                type="button"
                id="btn-reset-calculator"
                onClick={handleResetCalculator}
                className="text-xs text-slate-400 hover:text-slate-200 transition-colors font-semibold py-1 px-3 bg-slate-900 rounded-md border border-slate-850 cursor-pointer"
              >
                Reset Factors
              </button>
            </div>

            {/* LayoutGroup preserves state transition beautifully */}
            <LayoutGroup>
              <div className="space-y-4">
                {factors.map((factor) => (
                  <FactorCard
                    key={factor.id}
                    factor={factor}
                    onStatusChange={handleStatusChange}
                    onNotesChange={handleNotesChange}
                    onWeightChange={handleWeightChange}
                  />
                ))}
              </div>
            </LayoutGroup>

            {/* Educational Info Cards */}
            <div className="bg-slate-900/30 border border-slate-900 rounded-xl p-4 flex gap-3 text-xs leading-relaxed text-slate-400">
              <ShieldAlert className="w-5 h-5 text-sky-400 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="text-slate-300 font-medium">USME Smart Money Score Core Directives:</p>
                <p className="font-sans">
                  The Smart Money Score represents institutional commitment. A score of <strong className="text-emerald-400">90%+ (ELITE)</strong> requires alignment on almost all major variables (especially Higher Timeframe structure and CHoCH displacement). Do not force trades when SMT or HTF trends oppose your bias. Sit on your hands during low-volume sessions.
                </p>
              </div>
            </div>
          </section>

          {/* RIGHT: Scoring HUD, Advisory and Logs (Grid Column 5) */}
          <section className="lg:col-span-5 space-y-6">
            <div className="space-y-0.5">
              <h2 className="text-base font-bold text-slate-200 tracking-tight font-sans">
                Real-Time Trade Decision HUD
              </h2>
              <p className="text-xs text-slate-400 font-sans">
                Trade scoring classification, checklists, and logging.
              </p>
            </div>

            <ScoreSummary
              score={score}
              category={category}
              factors={factors}
              symbol={symbol}
              direction={direction}
              onSymbolChange={setSymbol}
              onDirectionChange={setDirection}
              journalNotes={journalNotes}
              onJournalNotesChange={setJournalNotes}
              onSaveSetup={handleSaveSetup}
            />

            <SavedSetups
              setups={savedSetups}
              onLoadSetup={handleLoadSetup}
              onDeleteSetup={handleDeleteSetup}
              onClearAll={handleClearAll}
              onImportSetups={handleImportSetups}
            />
          </section>

        </div>
      </main>

      {/* 3. Footer */}
      {/* Footer Status Bar */}
      <footer className="bg-slate-900 px-6 py-4 border-t border-slate-800 flex flex-col sm:flex-row justify-between items-center gap-3">
        <div className="flex gap-4">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)] animate-pulse"></span>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">SYST-READY</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></span>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">DATA-FEED: OK</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-700"></span>
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">SECURE-SANDBOX</span>
          </div>
        </div>
        <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
          UUID: 0x2199-F4-ICT-BOS-SMT-MASTER
        </div>
      </footer>
    </div>
  );
}

import React, { useEffect, useState } from 'react';
import { Copy, Server, CreditCard, Home, LifeBuoy, Plus, Send, ChevronRight, AlertCircle, ArrowLeft, RefreshCw, Shield, HelpCircle, Check, BookOpen, Bitcoin, CheckCircle } from 'lucide-react';
import { apiClient } from '../api/client';
import { PaymentSection } from '../components/PaymentSection';
import '../App.css';

interface Account {
  id: number;
  username: string;
  service_type: string;
  service_label: string;
  ssh_password?: string;
  uuid_token?: string;
  import_link?: string;
  connection_host?: string;
  connection_port?: number;
  connection_path?: string;
  connection_security?: string;
  server_id: number;
  traffic_used_gb: number;
  traffic_limit_gb: number | null;
  expires_at: string;
}

interface ShopServer {
  id: number;
  name: string;
  ip_address: string;
  ssh_port: number;
  service_type: string;
  service_label: string;
}

interface Ticket {
  id: number;
  subject: string;
  status: string;
  updated_at: string;
}

interface Message {
  id: number;
  sender: 'user' | 'admin';
  text: string;
  created_at: string;
}

interface ShopPlan {
  id: number;
  key: string;
  title: string;
  users: string;
  bandwidth: string;
  latency: string;
  location: string;
  priceToman: number;
  priceUsd: number;
  popular: boolean;
}

interface ShopOffer {
  key: string;
  plan: ShopPlan;
  server: ShopServer;
}

export const ClientDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'shop' | 'wallet' | 'support' | 'tutorial'>('dashboard');
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Copy feedback state
  const [copyFeedback, setCopyFeedback] = useState<{[key: string]: boolean}>({});

  // Support tickets state
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [ticketMessages, setTicketMessages] = useState<Message[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [replyText, setReplyText] = useState('');
  const [newTicketSubject, setNewTicketSubject] = useState('');
  const [newTicketMessage, setNewTicketMessage] = useState('');
  const [isCreatingTicket, setIsCreatingTicket] = useState(false);
  const [submittingTicket, setSubmittingTicket] = useState(false);
  const [selectedPlanKey, setSelectedPlanKey] = useState<string | null>(null);
  const [shopMethod, setShopMethod] = useState<'card' | 'crypto' | null>(null);
  const [shopReceiptFile, setShopReceiptFile] = useState<File | null>(null);
  const [shopDiscountCode, setShopDiscountCode] = useState('');
  const [shopDiscountApplied, setShopDiscountApplied] = useState(false);
  const [shopDiscountPercent, setShopDiscountPercent] = useState<number | null>(null);
  const [shopPayableToman, setShopPayableToman] = useState<number | null>(null);
  const [shopPayableUsd, setShopPayableUsd] = useState<number | null>(null);
  const [shopLoading, setShopLoading] = useState(false);
  const [shopStatus, setShopStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [shopError, setShopError] = useState('');

  // Vless configs loaded state
  const [vlessConfigs, setVlessConfigs] = useState<{[accountId: number]: string[]}>({});
  const [loadingConfigs, setLoadingConfigs] = useState<{[accountId: number]: boolean}>({});
  const [showQrCode, setShowQrCode] = useState<{[configIndex: string]: boolean}>({});

  const toggleConfigs = async (accountId: number, importLink: string) => {
    if (vlessConfigs[accountId]) {
      setVlessConfigs(prev => {
        const copy = { ...prev };
        delete copy[accountId];
        return copy;
      });
      return;
    }
    
    setLoadingConfigs(prev => ({ ...prev, [accountId]: true }));
    try {
      const token = importLink.split('/sub/')[1];
      const res = await apiClient.get(`/sub/${token}`, { baseURL: '/' });
      const decoded = atob(res.data);
      const links = decoded.split('\n').map(l => l.trim()).filter(l => l.startsWith('vless://'));
      setVlessConfigs(prev => ({ ...prev, [accountId]: links }));
    } catch (err) {
      console.error("Error loading configs", err);
      alert("خطا در دریافت تنظیمات کانفیگ. لطفاً دوباره تلاش کنید.");
    } finally {
      setLoadingConfigs(prev => ({ ...prev, [accountId]: false }));
    }
  };

  const getRemark = (link: string) => {
    const parts = link.split('#');
    if (parts.length < 2) return 'VLESS Reality';
    const rawRemark = decodeURIComponent(parts[1]);
    const remarkParts = rawRemark.split('|');
    if (remarkParts.length >= 2) {
      return remarkParts[1].trim();
    }
    return rawRemark;
  };

  const fetchDashboard = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get('/webapp/dashboard');
      setDashboardData(res.data);
    } catch (err: any) {
      console.error("Error fetching dashboard", err);
      const status = err.response?.status;
      const detail = err.response?.data?.detail;
      setError(`خطا در دریافت اطلاعات (کد: ${status || 'شبکه'}). جزئیات: ${typeof detail === 'object' ? JSON.stringify(detail) : detail || 'عدم اتصال به سرور'}`);
    } finally {
      setLoading(false);
    }
  };

  const fetchTickets = async () => {
    try {
      const res = await apiClient.get('/webapp/tickets');
      setTickets(res.data.tickets || []);
    } catch (err) {
      console.error("Error fetching tickets", err);
    }
  };

  const fetchTicketMessages = async (ticketId: number) => {
    setLoadingMessages(true);
    try {
      const res = await apiClient.get(`/webapp/tickets/${ticketId}/messages`);
      setTicketMessages(res.data.messages || []);
    } catch (err) {
      console.error("Error fetching messages", err);
    } finally {
      setLoadingMessages(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
    fetchTickets();
  }, []);

  useEffect(() => {
    if (activeTab === 'support' && !selectedTicket) {
      fetchTickets();
    }
  }, [activeTab, selectedTicket]);

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopyFeedback(prev => ({ ...prev, [label]: true }));
    setTimeout(() => {
      setCopyFeedback(prev => ({ ...prev, [label]: false }));
    }, 2000);
  };

  const formatPrice = (num: number) => {
    return num.toLocaleString('fa-IR') + ' تومان';
  };

  const handleCreateTicket = async () => {
    if (!newTicketSubject.trim() || !newTicketMessage.trim()) return;
    setSubmittingTicket(true);
    try {
      const res = await apiClient.post('/webapp/tickets', {
        subject: newTicketSubject,
        message: newTicketMessage
      });
      setNewTicketSubject('');
      setNewTicketMessage('');
      setIsCreatingTicket(false);
      await fetchTickets();
      // Select the newly created ticket
      const newTicket: Ticket = {
        id: res.data.ticket_id,
        subject: newTicketSubject,
        status: 'open',
        updated_at: new Date().toISOString()
      };
      setSelectedTicket(newTicket);
      await fetchTicketMessages(newTicket.id);
    } catch (err) {
      alert("خطا در ایجاد تیکت پشتیبانی. لطفا دوباره تلاش کنید.");
    } finally {
      setSubmittingTicket(false);
    }
  };

  const handleSendReply = async () => {
    if (!replyText.trim() || !selectedTicket) return;
    const currentReply = replyText;
    setReplyText('');
    try {
      await apiClient.post(`/webapp/tickets/${selectedTicket.id}/messages`, {
        text: currentReply
      });
      // Refresh messages
      await fetchTicketMessages(selectedTicket.id);
    } catch (err) {
      alert("خطا در ارسال پیام.");
      setReplyText(currentReply);
    }
  };

  const renderDashboardCard = (acc: Account) => {
    const limit = acc.traffic_limit_gb;
    const used = acc.traffic_used_gb;
    const percentage = limit ? Math.min((used / limit) * 100, 100) : 0;
    const importLink = acc.import_link || '';
    const isV2Ray = acc.service_type === 'v2ray';
    
    // Check if account is expired
    const isExpired = new Date(acc.expires_at).getTime() < new Date().getTime();
    
    // SVG Progress Arc Config
    const radius = 26;
    const circumference = 2 * Math.PI * radius;
    const strokeDashoffset = limit ? circumference - (percentage / 100) * circumference : 0;

    const loadedLinks = vlessConfigs[acc.id] || [];
    const isLoadingLinks = loadingConfigs[acc.id] || false;

    return (
      <div key={acc.id} className="relative glass-panel rounded-3xl p-5 border border-white/10 overflow-hidden shadow-xl animate-slide-up hover:border-white/20 transition-all duration-300">
        {/* Decorative backdrop light effect */}
        <div className="absolute -top-12 -left-12 w-28 h-28 bg-indigo-600/10 rounded-full blur-2xl pointer-events-none" />

        {/* Card Header */}
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-slate-900/40 text-indigo-400 rounded-xl flex items-center justify-center border border-white/5 shadow-inner">
              <Shield size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-extrabold text-white text-base font-mono">{acc.username}</h3>
                <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold border ${
                  isV2Ray
                    ? 'bg-indigo-500/10 text-indigo-300 border-indigo-500/20'
                    : 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                }`}>
                  {acc.service_label}
                </span>
              </div>
              <p className="text-[10px] text-gray-400 flex items-center gap-1 mt-0.5">
                <span>پایان اعتبار:</span>
                <span className="font-bold text-slate-300">
                  {new Date(acc.expires_at).toLocaleDateString('fa-IR')}
                </span>
              </p>
            </div>
          </div>

          {/* Circle Gauge for Limits */}
          <div className="relative flex items-center justify-center">
            {limit !== null ? (
              <>
                <svg className="w-14 h-14 transform -rotate-90">
                  <circle cx="28" cy="28" r={radius} stroke="currentColor" strokeWidth="4.5" fill="transparent" className="text-slate-800" />
                  <circle cx="28" cy="28" r={radius} stroke="currentColor" strokeWidth="4.5" fill="transparent"
                    strokeDasharray={circumference}
                    strokeDashoffset={strokeDashoffset}
                    className={`${percentage > 85 ? 'text-rose-500' : percentage > 60 ? 'text-amber-500' : 'text-indigo-400'} transition-all duration-1000 ease-in-out`}
                  />
                </svg>
                <div className="absolute flex flex-col items-center justify-center text-[9px] text-slate-300">
                  <span className="font-extrabold">{used.toFixed(1)}G</span>
                  <span className="text-gray-500 text-[7px]">از {limit}G</span>
                </div>
              </>
            ) : (
              <div className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-1 rounded-full text-[10px] font-bold">
                نامحدود
              </div>
            )}
          </div>
        </div>

        {/* Connection Details */}
        <div className="space-y-4 bg-slate-950/40 p-4 rounded-2xl border border-white/5">
          {isV2Ray ? (
            <>
              <div className="flex flex-col gap-1.5 text-xs text-right">
                <span className="text-gray-400 font-bold">🔗 لینک سابسکریپشن V2Ray / VLESS:</span>
                <div className="flex gap-2 items-center bg-slate-950/80 p-2.5 rounded-xl border border-white/5 mt-1">
                  <button 
                    onClick={() => handleCopy(importLink, acc.username + '_sublink')}
                    className="bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300 border border-indigo-500/30 px-3 py-1.5 rounded-xl font-bold flex items-center gap-1 transition-all active:scale-[0.98] shrink-0"
                  >
                    {copyFeedback[acc.username + '_sublink'] ? (
                      <>
                        <Check size={12} className="text-green-400" />
                        <span>کپی شد!</span>
                      </>
                    ) : (
                      <>
                        <Copy size={12} />
                        <span>کپی لینک</span>
                      </>
                    )}
                  </button>
                  <span className="font-mono text-slate-300 truncate text-[10px] select-all flex-1 text-left" dir="ltr">
                    {importLink}
                  </span>
                </div>
                <p className="text-[10px] text-gray-500 leading-normal mt-1 text-right">
                  کافیست لینک بالا را در نرم‌افزار خود مانند V2Box، v2rayNG یا Shadowrocket ایمپورت و بروزرسانی کنید.
                </p>
              </div>

              <div className="border-t border-white/5 pt-3">
                <button
                  onClick={() => toggleConfigs(acc.id, importLink)}
                  disabled={isLoadingLinks}
                  className="w-full bg-slate-900/60 hover:bg-indigo-600/25 text-slate-300 hover:text-indigo-300 border border-white/10 rounded-xl py-2 px-4 text-xs font-bold transition-all flex items-center justify-center gap-2 active:scale-[0.99]"
                >
                  {isLoadingLinks ? (
                    <>
                      <RefreshCw className="animate-spin" size={13} />
                      <span>در حال دریافت...</span>
                    </>
                  ) : loadedLinks.length > 0 ? (
                    <span>▲ پنهان کردن کانفیگ‌های تکی</span>
                  ) : (
                    <span>▼ مشاهده کانفیگ‌های تکی و QR Code</span>
                  )}
                </button>
                
                {loadedLinks.length > 0 && (
                  <div className="mt-3 space-y-3 max-h-72 overflow-y-auto pr-1">
                    {loadedLinks.map((link, idx) => {
                      const remarkName = getRemark(link);
                      const isDirect = remarkName.toLowerCase().includes('direct');
                      const qrKey = `${acc.id}_${idx}`;
                      const isQrOpen = !!showQrCode[qrKey];
                      
                      return (
                        <div key={idx} className="bg-slate-950/80 p-3 rounded-xl border border-white/5 text-right space-y-2">
                          <div className="flex justify-between items-center text-xs">
                            <span className={`px-2 py-0.5 rounded-md text-[9px] font-extrabold ${
                              isDirect ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/10' : 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/10'
                            }`}>
                              {isDirect ? 'اتصال مستقیم' : 'اتصال تونل'}
                            </span>
                            <span className="font-extrabold text-white text-[11px] font-sans">{remarkName}</span>
                          </div>
                          
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleCopy(link, `${acc.id}_link_${idx}`)}
                              className="flex-1 bg-white/5 hover:bg-white/10 text-slate-300 border border-white/10 rounded-lg py-1.5 px-2 text-[10px] font-bold transition-all flex items-center justify-center gap-1"
                            >
                              {copyFeedback[`${acc.id}_link_${idx}`] ? (
                                <>
                                  <Check size={11} className="text-green-400" />
                                  <span>کپی شد!</span>
                                </>
                              ) : (
                                <>
                                  <Copy size={11} />
                                  <span>کپی کانفیگ VLESS</span>
                                </>
                              )}
                            </button>
                            
                            <button
                              onClick={() => setShowQrCode(prev => ({ ...prev, [qrKey]: !isQrOpen }))}
                              className="bg-white/5 hover:bg-white/10 text-slate-300 border border-white/10 rounded-lg py-1.5 px-3 text-[10px] font-bold transition-all flex items-center justify-center"
                            >
                              {isQrOpen ? 'پنهان کردن بارکد' : 'نمایش بارکد QR'}
                            </button>
                          </div>

                          {isQrOpen && (
                            <div className="flex flex-col items-center justify-center p-3 bg-white rounded-xl mt-2 animate-fade-in mx-auto w-48 h-48">
                              <img 
                                src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(link)}`} 
                                alt="QR Code" 
                                className="w-40 h-40"
                              />
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="space-y-3 text-xs text-right">
              <div className="grid grid-cols-1 gap-2">
                <div className="bg-slate-950/80 p-3 rounded-xl border border-white/5">
                  <span className="text-gray-400 block mb-1">هاست یا IP</span>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-slate-200 text-[11px]" dir="ltr">{acc.connection_host || '-'}</span>
                    <button onClick={() => handleCopy(acc.connection_host || '', `${acc.id}_host`)} className="text-indigo-300 text-[10px] font-bold">کپی</button>
                  </div>
                </div>
                <div className="bg-slate-950/80 p-3 rounded-xl border border-white/5">
                  <span className="text-gray-400 block mb-1">نام کاربری SSH</span>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-slate-200 text-[11px]" dir="ltr">{acc.username}</span>
                    <button onClick={() => handleCopy(acc.username, `${acc.id}_username`)} className="text-indigo-300 text-[10px] font-bold">کپی</button>
                  </div>
                </div>
                <div className="bg-slate-950/80 p-3 rounded-xl border border-white/5">
                  <span className="text-gray-400 block mb-1">رمز عبور</span>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-slate-200 text-[11px]" dir="ltr">{acc.ssh_password || '-'}</span>
                    <button onClick={() => handleCopy(acc.ssh_password || '', `${acc.id}_password`)} className="text-indigo-300 text-[10px] font-bold">کپی</button>
                  </div>
                </div>
                <div className="bg-slate-950/80 p-3 rounded-xl border border-white/5">
                  <span className="text-gray-400 block mb-1">پورت</span>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-slate-200 text-[11px]" dir="ltr">{acc.connection_port || 22}</span>
                    <button onClick={() => handleCopy(String(acc.connection_port || 22), `${acc.id}_port`)} className="text-indigo-300 text-[10px] font-bold">کپی</button>
                  </div>
                </div>
              </div>
              <p className="text-[10px] text-gray-500 leading-normal">
                برای این سرویس از کلاینت SSH یا نرم‌افزارهای تونل SSH استفاده کنید. اطلاعات بالا فقط مربوط به خریداران سرویس SSH است.
              </p>
            </div>
          )}
        </div>

        {/* Dynamic Status / Actions footer */}
        <div className="flex justify-between items-center mt-4 pt-1">
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${isExpired ? 'bg-rose-500' : 'bg-emerald-500 status-dot-active'}`} />
            <span className={`text-[11px] font-bold ${isExpired ? 'text-rose-400' : 'text-emerald-400'}`}>
              {isExpired ? 'منقضی شده' : 'متصل به شبکه'}
            </span>
          </div>
          <button 
            onClick={() => setActiveTab('shop')}
            className="bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/20 px-4 py-1.5 rounded-xl text-xs font-bold transition-all"
          >
            تمدید / تغییر طرح
          </button>
        </div>
      </div>
    );
  };

  const renderDashboardTab = () => {
    if (loading) {
      return (
        <div className="flex flex-col items-center justify-center py-20 space-y-4">
          <div className="relative flex items-center justify-center">
            <div className="w-10 h-10 border-t-2 border-r-2 border-indigo-500 rounded-full animate-spin" />
            <Shield className="absolute text-indigo-400 animate-pulse" size={16} />
          </div>
          <span className="text-xs text-gray-400">در حال به روز رسانی اطلاعات کاربری...</span>
        </div>
      );
    }

    if (error) {
      const hasTelegram = !!window.Telegram?.WebApp;
      const initDataLength = window.Telegram?.WebApp?.initData?.length || 0;
      return (
        <div className="p-4 space-y-4 max-w-md mx-auto">
          <div className="bg-rose-500/10 border border-rose-500/20 p-6 rounded-3xl text-center space-y-4 relative overflow-hidden animate-slide-up shadow-lg">
            <div className="w-12 h-12 bg-rose-500/10 text-rose-400 rounded-full flex items-center justify-center mx-auto border border-rose-500/20">
              <AlertCircle size={24} />
            </div>
            <div className="text-rose-400 text-base font-extrabold">خطا در ارتباط با سرور</div>
            <div className="text-[10px] text-rose-300/80 font-mono dir-ltr break-all bg-black/30 p-3.5 rounded-xl border border-white/5">{error}</div>
            
            <div className="bg-slate-950/50 p-4 rounded-2xl text-xs space-y-2 text-right text-gray-400 font-mono border border-white/5">
              <div className="flex justify-between">
                <span>SDK تلگرام:</span>
                <span className={hasTelegram ? "text-emerald-400" : "text-rose-400"}>{hasTelegram ? "✅ متصل" : "❌ قطع"}</span>
              </div>
              <div className="flex justify-between">
                <span>حجم امضا:</span>
                <span className="text-white">{initDataLength} کاراکتر</span>
              </div>
            </div>

            <button onClick={fetchDashboard} className="w-full bg-gradient-premium text-white py-3 rounded-2xl font-bold text-sm transition-all duration-200 active:scale-[0.98] shadow-lg shadow-indigo-600/30">
              🔄 تلاش مجدد
            </button>
          </div>
        </div>
      );
    }

    const accounts = dashboardData?.accounts || [];

    return (
      <div className="space-y-6 max-w-md mx-auto animate-fade-in">
        {/* Welcome Wallet Widget */}
        <div className="relative overflow-hidden bg-gradient-premium rounded-3xl p-6 shadow-2xl text-white shadow-indigo-600/20 border border-white/10">
          <div className="absolute top-0 right-0 w-36 h-36 bg-white/5 rounded-full blur-3xl pointer-events-none" />
          
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[10px] text-indigo-200 uppercase font-semibold">موجودی کیف پول</span>
              <h1 className="text-2xl font-black font-sans tracking-wide mt-1">
                {formatPrice(dashboardData?.balance || 0)}
              </h1>
            </div>
            <button 
              onClick={() => setActiveTab('wallet')}
              className="bg-white/10 hover:bg-white/20 px-3 py-1.5 rounded-xl text-xs font-bold transition-all border border-white/10 flex items-center gap-1 active:scale-95"
            >
              <CreditCard size={13} /> شارژ حساب
            </button>
          </div>

          <div className="mt-6 pt-4 border-t border-white/10 flex justify-between items-center text-xs text-indigo-100">
            <span>شناسه کاربری شما:</span>
            <span className="font-bold font-mono">#{dashboardData?.user_id || '---'}</span>
          </div>
        </div>

        {/* Services Section */}
        <div className="space-y-4">
          <div className="flex justify-between items-center px-1">
            <h2 className="text-base font-extrabold text-white">سرویس‌های من</h2>
            <span className="bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-2 py-0.5 rounded-md text-[10px] font-bold">
              {accounts.length} اکانت فعال
            </span>
          </div>

          {accounts.length === 0 ? (
            <div className="glass-panel text-center py-12 px-6 rounded-3xl border border-white/5 flex flex-col items-center justify-center space-y-4">
              <div className="w-12 h-12 bg-white/5 text-gray-500 rounded-full flex items-center justify-center border border-white/5">
                <Server size={20} />
              </div>
              <div>
                <h3 className="font-bold text-white text-sm">طرح فعالی ندارید</h3>
                <p className="text-xs text-gray-400 mt-1 max-w-[200px] mx-auto leading-relaxed">
                  شما در حال حاضر فاقد اشتراک فعال هستید. جهت سفارش روی دکمه زیر کلیک کنید.
                </p>
              </div>
              <button 
                onClick={() => setActiveTab('shop')}
                className="bg-gradient-premium text-white px-5 py-2 rounded-2xl text-xs font-bold transition-all shadow-md active:scale-95"
              >
                خرید اشتراک جدید
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {accounts.map((acc: Account) => renderDashboardCard(acc))}
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderShopTab = () => {
    const plans: ShopPlan[] = [
      {
        id: 1,
        key: 'plan_5gb',
        title: 'BNETS PRO (5GB) 1Month',
        users: '۱ کاربر',
        bandwidth: '۵ گیگابایت ترافیک',
        latency: 'سرعت و پایداری بالا (مناسب وب‌گردی و چت)',
        location: 'انگلیس-لندن🇬🇧',
        priceToman: 98000,
        priceUsd: 1,
        popular: false,
      },
      {
        id: 2,
        key: 'plan_10gb',
        title: 'BNETS PRO (10GB) 1Month',
        users: '۱ کاربر',
        bandwidth: '۱۰ گیگابایت ترافیک',
        latency: 'سرعت و پایداری بالا (مناسب یوتیوب و وب‌گردی)',
        location: 'انگلیس-لندن🇬🇧',
        priceToman: 188000,
        priceUsd: 2,
        popular: false,
      },
      {
        id: 3,
        key: 'plan_20gb',
        title: 'BNETS PRO (20GB) 1Month',
        users: '۲ کاربر همزمان',
        bandwidth: '۲۰ گیگابایت ترافیک',
        latency: 'سرعت فوق العاده (مناسب اینستاگرام و یوتیوب)',
        location: 'انگلیس-لندن🇬🇧',
        priceToman: 268000,
        priceUsd: 3,
        popular: true,
      },
      {
        id: 4,
        key: 'plan_30gb',
        title: 'BNETS PRO (30GB) 1Month',
        users: '۲ کاربر همزمان',
        bandwidth: '۳۰ گیگابایت ترافیک',
        latency: 'کیفیت عالی (مناسب اینستاگرام و تماشای فیلم)',
        location: 'انگلیس-لندن🇬🇧',
        priceToman: 358000,
        priceUsd: 4,
        popular: false,
      },
      {
        id: 5,
        key: 'plan_50gb',
        title: 'BNETS PRO (50GB) 1Month',
        users: '۳ کاربر همزمان',
        bandwidth: '۵۰ گیگابایت ترافیک',
        latency: 'سرعت حرفه‌ای (مناسب دانلود و بازی‌های آنلاین)',
        location: 'انگلیس-لندن🇬🇧',
        priceToman: 498000,
        priceUsd: 5,
        popular: false,
      },
      {
        id: 6,
        key: 'plan_100gb',
        title: 'BNETS PRO (100GB) 1Month',
        users: '۴ کاربر همزمان',
        bandwidth: '۱۰۰ گیگابایت ترافیک',
        latency: 'بالاترین کیفیت و سرعت (بدون محدودیت)',
        location: 'انگلیس-لندن🇬🇧',
        priceToman: 698000,
        priceUsd: 7,
        popular: false,
      }
    ];
    const shopServers: ShopServer[] = dashboardData?.available_servers || [];
    const selectedOffer: ShopOffer | null = (() => {
      if (!selectedPlanKey) return null;
      for (const server of shopServers) {
        for (const plan of plans) {
          const offerKey = `${server.id}:${plan.key}`;
          if (offerKey === selectedPlanKey) {
            return { key: offerKey, server, plan };
          }
        }
      }
      return null;
    })();
    const systemCard = '5859831130851222';
    const systemName = 'امیرحسین نادری';

    const startPlanCheckout = (offerKey: string) => {
      setSelectedPlanKey(offerKey);
      setShopMethod(null);
      setShopReceiptFile(null);
      setShopDiscountCode('');
      setShopDiscountApplied(false);
      setShopDiscountPercent(null);
      setShopPayableToman(null);
      setShopPayableUsd(null);
      setShopStatus('idle');
      setShopError('');
    };

    const applyShopDiscount = async () => {
      if (!selectedOffer || !shopDiscountCode.trim()) {
        setShopStatus('error');
        setShopError('ابتدا سرویس و کد تخفیف را انتخاب کنید.');
        return;
      }
      try {
        const response = await apiClient.post('/webapp/payments/discount/preview', {
          plan_id: selectedOffer.plan.id,
          discount_code: shopDiscountCode.trim(),
          payment_method: shopMethod,
        });
        setShopDiscountApplied(true);
        setShopDiscountPercent(response.data?.percent_off ?? null);
        setShopPayableToman(response.data?.payable_toman ?? null);
        setShopPayableUsd(response.data?.payable_usd ?? null);
        setShopStatus('idle');
        setShopError('');
      } catch (err: any) {
        setShopDiscountApplied(false);
        setShopDiscountPercent(null);
        setShopPayableToman(null);
        setShopPayableUsd(null);
        setShopStatus('error');
        const detail = err.response?.data?.detail;
        setShopError(typeof detail === 'object' ? JSON.stringify(detail) : detail || 'کد تخفیف معتبر نیست.');
      }
    };

    const handleShopCardSubmit = async () => {
      if (!selectedOffer || !shopReceiptFile) {
        setShopStatus('error');
        setShopError('لطفاً فقط تصویر اسکرین‌شات رسید پرداخت را انتخاب کنید.');
        return;
      }

      setShopLoading(true);
      setShopStatus('idle');
      const formData = new FormData();
      formData.append('plan_id', selectedOffer.plan.id.toString());
      formData.append('server_id', selectedOffer.server.id.toString());
      if (shopDiscountCode.trim()) {
        formData.append('discount_code', shopDiscountCode.trim());
      }
      formData.append('file', shopReceiptFile);

      try {
        await apiClient.post('/webapp/payments/charge', formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        });
        setShopStatus('success');
        setShopReceiptFile(null);
      } catch (err: any) {
        setShopStatus('error');
        const detail = err.response?.data?.detail;
        setShopError(typeof detail === 'object' ? JSON.stringify(detail) : detail || 'خطا در ثبت سفارش. لطفا مجددا تلاش کنید.');
      } finally {
        setShopLoading(false);
      }
    };

    const handleShopCryptoSubmit = async () => {
      if (!selectedOffer) return;
      setShopLoading(true);
      setShopStatus('idle');
      try {
        const response = await apiClient.post('/webapp/payments/plan/crypto', {
          plan_id: selectedOffer.plan.id,
          server_id: selectedOffer.server.id,
          discount_code: shopDiscountCode.trim() || undefined,
        });
        if (response.data?.url) {
          if (window.Telegram?.WebApp?.openLink) {
            window.Telegram.WebApp.openLink(response.data.url);
          } else {
            window.location.href = response.data.url;
          }
        } else {
          setShopStatus('error');
          setShopError('خطا در دریافت لینک درگاه پرداخت.');
        }
      } catch (err: any) {
        setShopStatus('error');
        const detail = err.response?.data?.detail;
        setShopError(typeof detail === 'object' ? JSON.stringify(detail) : detail || 'خطا در برقراری ارتباط با درگاه NOWPayments.');
      } finally {
        setShopLoading(false);
      }
    };

    return (
      <div className="space-y-6 max-w-md mx-auto animate-fade-in">
        <div className="text-center">
          <h2 className="text-xl font-extrabold text-gradient-purple">خرید سرویس VPN</h2>
          <p className="text-xs text-gray-400 mt-1">هر سرویس فقط برای همان نوع کاربر ساخته و مدیریت می‌شود: SSH یا PasarGuard V2Ray</p>
        </div>

        {shopServers.length === 0 ? (
          <div className="glass-panel text-center py-10 px-6 rounded-3xl border border-white/5 text-xs text-gray-400">
            در حال حاضر هیچ سرور فعالی برای فروش ثبت نشده است.
          </div>
        ) : (
          <div className="space-y-6">
            {shopServers.map((server) => (
              <div key={server.id} className="space-y-4">
                <div className="flex items-center justify-between px-1">
                  <div>
                    <h3 className="text-sm font-extrabold text-white">{server.name}</h3>
                    <p className="text-[10px] text-gray-400 mt-1" dir="ltr">{server.ip_address}:{server.ssh_port}</p>
                  </div>
                  <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold border ${
                    server.service_type === 'v2ray'
                      ? 'bg-indigo-500/10 text-indigo-300 border-indigo-500/20'
                      : 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                  }`}>
                    {server.service_label}
                  </span>
                </div>

                <div className="space-y-5">
                  {plans.map(p => {
                    const offerKey = `${server.id}:${p.key}`;
                    return (
                      <div 
                        key={offerKey}
                        className={`relative glass-panel rounded-3xl p-5 border overflow-hidden transition-all duration-300 ${
                          p.popular ? 'border-indigo-500/50 shadow-indigo-500/5' : 'border-white/10'
                        }`}
                      >
                        {p.popular && (
                          <div className="absolute top-3 left-3 bg-gradient-premium text-white text-[9px] font-extrabold px-2.5 py-1 rounded-full uppercase tracking-wider shadow-md">
                            پیشنهادی
                          </div>
                        )}

                        <h3 className="font-extrabold text-base text-white">{p.title}</h3>
                        <p className="text-xs text-indigo-300 font-bold mt-1">
                          {server.service_type === 'v2ray' ? 'مخصوص کاربران PasarGuard / V2Ray' : 'مخصوص کاربران SSH / VPS'}
                        </p>

                        <ul className="mt-4 space-y-2 text-xs text-gray-300 border-t border-white/5 pt-4">
                          <li className="flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                            <span>قابلیت اتصال: <strong>{p.users}</strong></span>
                          </li>
                          <li className="flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                            <span>ترافیک ماهانه: <strong>{p.bandwidth}</strong></span>
                          </li>
                          <li className="flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                            <span className="text-slate-400">{p.latency}</span>
                          </li>
                        </ul>

                        <div className="mt-6 flex items-center justify-between">
                          <div>
                            <span className="block text-[9px] text-gray-400">قیمت سرویس</span>
                            <span className="text-xs font-black text-white font-sans">
                              {formatPrice(p.priceToman)} / ${p.priceUsd.toFixed(2)}
                            </span>
                          </div>
                          <button 
                            onClick={() => startPlanCheckout(offerKey)}
                            className="bg-gradient-premium text-white font-bold px-6 py-2.5 rounded-2xl text-xs shadow-lg shadow-indigo-600/30 active:scale-[0.97] transition-all"
                          >
                            ثبت سفارش
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {selectedOffer && (
          <div className="glass-panel rounded-3xl p-5 border border-white/10 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-extrabold text-base text-white">{selectedOffer.plan.title}</h3>
                <p className="text-xs text-gray-400 mt-1">
                  {selectedOffer.server.service_label} • {selectedOffer.server.name}
                </p>
              </div>
              <button
                onClick={() => {
                  setSelectedPlanKey(null);
                  setShopMethod(null);
                  setShopReceiptFile(null);
                  setShopStatus('idle');
                  setShopError('');
                }}
                className="text-xs text-gray-400 hover:text-white"
              >
                بستن
              </button>
            </div>

            {!shopMethod ? (
              <div className="space-y-3">
                <button
                  onClick={() => {
                    setShopMethod('card');
                    setShopDiscountApplied(false);
                    setShopPayableToman(null);
                    setShopStatus('idle');
                    setShopError('');
                  }}
                  className="w-full bg-slate-900/60 border border-white/10 rounded-2xl px-4 py-3 text-sm font-bold text-white hover:border-indigo-500/40 transition-all"
                >
                  <CreditCard size={16} className="inline ml-2 text-indigo-400" />
                  کارت به کارت
                </button>
                <button
                  onClick={() => {
                    setShopMethod('crypto');
                    setShopDiscountApplied(false);
                    setShopPayableUsd(null);
                    setShopStatus('idle');
                    setShopError('');
                  }}
                  className="w-full bg-slate-900/60 border border-white/10 rounded-2xl px-4 py-3 text-sm font-bold text-white hover:border-indigo-500/40 transition-all"
                >
                  <Bitcoin size={16} className="inline ml-2 text-indigo-400" />
                  پرداخت ارز دیجیتال
                </button>
              </div>
            ) : shopMethod === 'card' ? (
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="block text-xs font-bold text-indigo-300">کد تخفیف</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={shopDiscountCode}
                      onChange={(e) => {
                        setShopDiscountCode(e.target.value.toUpperCase());
                        setShopDiscountApplied(false);
                        setShopPayableToman(null);
                      }}
                      placeholder="اختیاری"
                      className="flex-1 bg-slate-950/60 border border-white/10 rounded-2xl px-4 py-3 text-center font-bold text-white focus:outline-none focus:border-indigo-500 transition-all"
                    />
                    <button onClick={applyShopDiscount} type="button" className="px-4 py-3 rounded-2xl text-xs font-bold bg-white/5 border border-white/10 text-white">
                      اعمال
                    </button>
                  </div>
                </div>

                <div className="bg-slate-950/40 p-4 rounded-2xl border border-white/5 text-right space-y-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-400">روش پرداخت:</span>
                    <span className="font-bold text-white">کارت به کارت</span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-400">مبلغ قابل پرداخت:</span>
                    <span className="font-bold text-indigo-400">{formatPrice(shopPayableToman ?? selectedOffer.plan.priceToman)}</span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-400">شماره کارت:</span>
                    <button
                      onClick={() => handleCopy(systemCard, 'shop-card')}
                      className="font-mono text-white font-bold"
                    >
                      {systemCard}
                    </button>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-400">صاحب کارت:</span>
                    <span className="font-bold text-white">{systemName}</span>
                  </div>
                </div>

                {shopDiscountApplied && shopPayableToman !== null && (
                  <div className="bg-emerald-500/10 text-emerald-300 p-3 rounded-2xl text-xs border border-emerald-500/20">
                    مبلغ با {shopDiscountPercent}% تخفیف محاسبه شد.
                  </div>
                )}

                <div className="space-y-1.5">
                  <label className="block text-xs font-bold text-indigo-300">تصویر رسید پرداخت (اسکرین‌شات)</label>
                  <label className="flex flex-col items-center justify-center w-full h-28 border-2 border-dashed rounded-2xl cursor-pointer hover:bg-slate-900/30 border-white/10 hover:border-indigo-500/50 transition-colors">
                    <p className="text-[10px] text-gray-400 text-center px-4 truncate max-w-full">
                      {shopReceiptFile ? (
                        <span className="text-indigo-400 font-bold">{shopReceiptFile.name}</span>
                      ) : (
                        <span>فقط تصویر اسکرین‌شات رسید همین پرداخت را انتخاب کنید</span>
                      )}
                    </p>
                    <input
                      type="file"
                      className="hidden"
                      accept="image/*"
                      onChange={(e) => {
                        if (e.target.files && e.target.files.length > 0) {
                          const file = e.target.files[0];
                          if (!file.type.startsWith('image/')) {
                            alert('فقط فایل‌های تصویری اسکرین‌شات مجاز هستند.');
                            e.target.value = '';
                            return;
                          }
                          setShopReceiptFile(file);
                        }
                      }}
                    />
                  </label>
                </div>

                {shopStatus === 'success' && (
                  <div className="bg-emerald-500/10 text-emerald-400 p-3.5 rounded-2xl text-xs flex items-center border border-emerald-500/20">
                    <CheckCircle size={15} className="ml-2 shrink-0" />
                    سفارش شما ثبت شد و پس از تایید مدیریت، سرویس برای شما فعال خواهد شد.
                  </div>
                )}

                {shopStatus === 'error' && (
                  <div className="bg-rose-500/10 text-rose-400 p-3.5 rounded-2xl text-xs flex items-center border border-rose-500/20">
                    <AlertCircle size={15} className="ml-2 shrink-0" />
                    {shopError}
                  </div>
                )}

                <button
                  onClick={handleShopCardSubmit}
                  disabled={!shopReceiptFile || shopLoading}
                  className={`w-full font-bold py-3.5 rounded-2xl text-sm flex justify-center items-center transition-all duration-300 ${
                    shopReceiptFile && !shopLoading
                      ? 'bg-gradient-premium text-white shadow-lg shadow-indigo-600/30 active:scale-[0.98]'
                      : 'bg-slate-800 text-gray-500 cursor-not-allowed border border-white/5'
                  }`}
                >
                  {shopLoading ? (
                    <>
                      <RefreshCw className="animate-spin ml-2" size={16} />
                      در حال ثبت سفارش...
                    </>
                  ) : 'ثبت سفارش کارت به کارت'}
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="block text-xs font-bold text-indigo-300">کد تخفیف</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={shopDiscountCode}
                      onChange={(e) => {
                        setShopDiscountCode(e.target.value.toUpperCase());
                        setShopDiscountApplied(false);
                        setShopPayableUsd(null);
                      }}
                      className="flex-1 bg-slate-950/60 border border-white/10 rounded-2xl px-4 py-3 text-center font-bold text-white focus:outline-none focus:border-indigo-500 transition-all"
                      placeholder="اختیاری"
                    />
                    <button onClick={applyShopDiscount} type="button" className="px-4 py-3 rounded-2xl text-xs font-bold bg-white/5 border border-white/10 text-white">
                      اعمال
                    </button>
                  </div>
                </div>

                <div className="bg-slate-950/40 p-4 rounded-2xl border border-white/5 text-right space-y-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-400">روش پرداخت:</span>
                    <span className="font-bold text-white">پرداخت ارز دیجیتال</span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-400">مبلغ قابل پرداخت:</span>
                    <span className="font-bold text-indigo-400 font-mono">${(shopPayableUsd ?? selectedOffer.plan.priceUsd).toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-400">سرویس:</span>
                    <span className="font-bold text-white">{selectedOffer.server.service_label}</span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-400">پلن:</span>
                    <span className="font-bold text-white">{selectedOffer.plan.title}</span>
                  </div>
                </div>

                {shopStatus === 'error' && (
                  <div className="bg-rose-500/10 text-rose-400 p-3.5 rounded-2xl text-xs flex items-center border border-rose-500/20">
                    <AlertCircle size={15} className="ml-2 shrink-0" />
                    {shopError}
                  </div>
                )}

                <button
                  onClick={handleShopCryptoSubmit}
                  disabled={shopLoading}
                  className={`w-full font-bold py-3.5 rounded-2xl text-sm flex justify-center items-center transition-all duration-300 ${
                    !shopLoading
                      ? 'bg-gradient-premium text-white shadow-lg shadow-indigo-600/30 active:scale-[0.98]'
                      : 'bg-slate-800 text-gray-500 cursor-not-allowed border border-white/5'
                  }`}
                >
                  {shopLoading ? (
                    <>
                      <RefreshCw className="animate-spin ml-2" size={16} />
                      در حال اتصال به درگاه...
                    </>
                  ) : 'پرداخت با NOWPayments'}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderSupportTab = () => {
    if (selectedTicket) {
      return (
        <div className="flex flex-col h-[calc(100vh-140px)] max-w-md mx-auto animate-fade-in">
          {/* Back Header */}
          <div className="flex justify-between items-center pb-3 border-b border-white/5 mb-3">
            <div className="flex items-center gap-2">
              <button 
                onClick={() => {
                  setSelectedTicket(null);
                  setTicketMessages([]);
                }} 
                className="w-8 h-8 rounded-xl bg-white/5 border border-white/5 text-gray-300 flex items-center justify-center hover:bg-white/10 active:scale-90 transition-all"
              >
                <ArrowLeft size={16} />
              </button>
              <div>
                <h3 className="font-extrabold text-sm text-white truncate max-w-[180px]">{selectedTicket.subject}</h3>
                <span className="text-[9px] text-gray-500">کد رهگیری: #{selectedTicket.id}</span>
              </div>
            </div>
            <span className={`text-[9px] font-extrabold px-2 py-0.5 rounded-full border ${
              selectedTicket.status === 'open' 
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' 
                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            }`}>
              {selectedTicket.status === 'open' ? 'درحال بررسی' : 'پاسخ داده شده'}
            </span>
          </div>

          {/* Messages list */}
          <div className="flex-1 overflow-y-auto space-y-3 pl-1 pr-1 custom-scrollbar mb-3">
            {loadingMessages ? (
              <div className="flex justify-center items-center py-10">
                <RefreshCw className="animate-spin text-indigo-400" size={16} />
              </div>
            ) : ticketMessages.length === 0 ? (
              <div className="text-center text-xs text-gray-500 py-10">پیامی یافت نشد.</div>
            ) : (
              ticketMessages.map(m => {
                const isAdmin = m.sender === 'admin';
                return (
                  <div key={m.id} className={`flex flex-col ${isAdmin ? 'items-start' : 'items-end'}`}>
                    <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-xs shadow-sm ${
                      isAdmin 
                        ? 'bg-slate-800 text-slate-100 rounded-tl-sm border border-white/5' 
                        : 'bg-indigo-600 text-white rounded-tr-sm shadow-indigo-600/5'
                    }`}>
                      <p className="leading-relaxed whitespace-pre-wrap">{m.text}</p>
                    </div>
                    <span className="text-[8px] text-gray-500 mt-1 font-mono">
                      {new Date(m.created_at).toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                );
              })
            )}
          </div>

          {/* Reply Form */}
          <div className="bg-slate-900/50 p-2.5 rounded-2xl border border-white/5 flex items-center backdrop-blur-xl">
            <input 
              type="text" 
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              placeholder="پاسخ خود را اینجا بنویسید..."
              className="flex-1 bg-transparent text-xs text-white px-3 py-1.5 focus:outline-none placeholder-gray-500"
              onKeyDown={(e) => e.key === 'Enter' && handleSendReply()}
            />
            <button 
              onClick={handleSendReply} 
              disabled={!replyText.trim()}
              className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 transition-all ${
                replyText.trim() 
                  ? 'bg-gradient-premium text-white active:scale-90 shadow-lg shadow-indigo-600/20' 
                  : 'bg-slate-800 text-gray-500 border border-white/5'
              }`}
            >
              <Send size={14} className="-ml-0.5" />
            </button>
          </div>
        </div>
      );
    }

    if (isCreatingTicket) {
      return (
        <div className="space-y-5 max-w-md mx-auto animate-fade-in">
          <div className="flex justify-between items-center pb-2 border-b border-white/5">
            <h3 className="font-extrabold text-base text-white">ارسال تیکت جدید</h3>
            <button 
              onClick={() => setIsCreatingTicket(false)} 
              className="text-xs text-gray-400 hover:text-white"
            >
              انصراف
            </button>
          </div>

          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-gray-400">موضوع تیکت:</label>
              <input 
                type="text"
                placeholder="مثال: مشکل در تمدید اکانت"
                value={newTicketSubject}
                onChange={(e) => setNewTicketSubject(e.target.value)}
                className="w-full bg-slate-950/60 border border-white/10 rounded-2xl px-4 py-3 text-xs text-white focus:outline-none focus:border-indigo-500 transition-colors"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-gray-400">شرح درخواست شما:</label>
              <textarea 
                placeholder="توضیحات مشکل خود را در اینجا به تفصیل بیان فرمایید..."
                rows={5}
                value={newTicketMessage}
                onChange={(e) => setNewTicketMessage(e.target.value)}
                className="w-full bg-slate-950/60 border border-white/10 rounded-2xl px-4 py-3 text-xs text-white focus:outline-none focus:border-indigo-500 transition-colors resize-none leading-relaxed"
              />
            </div>

            <button 
              onClick={handleCreateTicket}
              disabled={!newTicketSubject.trim() || !newTicketMessage.trim() || submittingTicket}
              className={`w-full py-3.5 rounded-2xl text-xs font-extrabold flex justify-center items-center gap-1.5 transition-all duration-300 ${
                newTicketSubject.trim() && newTicketMessage.trim() && !submittingTicket
                  ? 'bg-gradient-premium text-white shadow-lg shadow-indigo-600/30 active:scale-[0.98]'
                  : 'bg-slate-800 text-gray-500 border border-white/5 cursor-not-allowed'
              }`}
            >
              {submittingTicket ? <RefreshCw className="animate-spin" size={14} /> : null}
              ثبت و ارسال تیکت
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-6 max-w-md mx-auto animate-fade-in">
        <div className="flex justify-between items-center px-1">
          <div>
            <h2 className="text-base font-extrabold text-white">تیکت‌های پشتیبانی</h2>
            <p className="text-[10px] text-gray-400 mt-0.5">درخواست‌های قبلی و ارتباط با مدیران</p>
          </div>
          <button 
            onClick={() => setIsCreatingTicket(true)}
            className="bg-gradient-premium text-white px-4 py-2 rounded-2xl text-xs font-bold transition-all shadow-lg shadow-indigo-600/20 active:scale-95 flex items-center gap-1"
          >
            <Plus size={14} /> ثبت تیکت جدید
          </button>
        </div>

        <div className="space-y-3">
          {tickets.length === 0 ? (
            <div className="glass-panel text-center py-10 px-6 rounded-3xl border border-white/5 flex flex-col items-center justify-center space-y-3">
              <div className="w-12 h-12 bg-white/5 text-gray-500 rounded-full flex items-center justify-center border border-white/5">
                <HelpCircle size={20} />
              </div>
              <p className="text-xs text-gray-400">تاکنون تیکت پشتیبانی ارسال نکرده‌اید.</p>
            </div>
          ) : (
            tickets.map(t => (
              <div 
                key={t.id} 
                onClick={() => {
                  setSelectedTicket(t);
                  fetchTicketMessages(t.id);
                }}
                className="glass-panel p-4 rounded-2xl border border-white/10 cursor-pointer hover:border-indigo-500/30 transition-all flex justify-between items-center active:scale-[0.99]"
              >
                <div className="space-y-1">
                  <h4 className="font-extrabold text-xs text-white line-clamp-1">{t.subject}</h4>
                  <div className="flex items-center gap-2 text-[9px] text-gray-500">
                    <span>کد تیکت: #{t.id}</span>
                    <span>•</span>
                    <span>{new Date(t.updated_at).toLocaleDateString('fa-IR')}</span>
                  </div>
                </div>
                
                <div className="flex items-center gap-2">
                  <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full border ${
                    t.status === 'open' 
                      ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' 
                      : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  }`}>
                    {t.status === 'open' ? 'درحال بررسی' : 'پاسخ داده شده'}
                  </span>
                  <ChevronRight size={14} className="text-gray-500" />
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    );
  };

  const renderTutorialTab = () => (
    <div className="space-y-6 animate-fade-in relative z-10">
      <div className="glass-panel p-6 rounded-3xl border border-indigo-500/20 shadow-[0_0_40px_rgba(99,102,241,0.1)] text-right">
        <h2 className="text-xl font-extrabold text-white mb-2 flex items-center justify-end gap-2">
          آموزش اتصال <BookOpen className="text-indigo-400" size={24} />
        </h2>
        <p className="text-gray-400 text-xs mb-6 leading-relaxed">
          این سرویس دو نوع محصول جدا دارد. خریدار SSH فقط از اطلاعات SSH استفاده می‌کند و خریدار PasarGuard فقط از لینک‌ها و کانفیگ‌های V2Ray استفاده می‌کند.
        </p>

        <div className="space-y-4">
          <div className="bg-emerald-500/10 p-4 rounded-2xl border border-emerald-500/20">
            <h3 className="font-bold text-emerald-300 mb-2 text-sm">سرویس SSH / VPS</h3>
            <p className="text-xs text-gray-300 leading-relaxed">
              در تب «سرویس‌های من» هاست، پورت، نام کاربری و رمز عبور نمایش داده می‌شود. این اطلاعات را در کلاینت SSH یا برنامه‌های تونل SSH وارد کنید. این بخش هیچ ارتباطی با کاربران PasarGuard ندارد.
            </p>
          </div>

          <div className="bg-indigo-500/10 p-4 rounded-2xl border border-indigo-500/20">
            <h3 className="font-bold text-indigo-300 mb-2 text-sm">سرویس PasarGuard / V2Ray</h3>
            <p className="text-xs text-gray-300 leading-relaxed">
              لینک سابسکریپشن را کپی یا QR را اسکن کنید. این بخش فقط برای خریداران V2Ray است و اطلاعات SSH در آن استفاده نمی‌شود.
            </p>
          </div>

          <div className="bg-slate-900/50 p-4 rounded-2xl border border-white/5">
            <h3 className="font-bold text-white mb-2 flex items-center justify-end gap-2 text-sm">کاربران iOS (آیفون و آیپد) <span className="text-xl">🍏</span></h3>
            <p className="text-xs text-gray-400 leading-relaxed">برنامه <b>V2Box</b> یا <b>Shadowrocket</b> یا <b>Streisand</b> را از App Store دانلود کرده و لینک سابسکریپشن کپی شده را اضافه کرده و بروزرسانی کنید.</p>
          </div>

          <div className="bg-slate-900/50 p-4 rounded-2xl border border-white/5">
            <h3 className="font-bold text-white mb-2 flex items-center justify-end gap-2 text-sm">کاربران Android (اندروید) <span className="text-xl">🤖</span></h3>
            <p className="text-xs text-gray-400 leading-relaxed">برنامه <b>v2rayNG</b> یا <b>Nekobox</b> را از Google Play/GitHub دانلود کرده و لینک سابسکریپشن خود را وارد کرده و بروزرسانی (Update subscription) کنید.</p>
          </div>

          <div className="bg-slate-900/50 p-4 rounded-2xl border border-white/5">
            <h3 className="font-bold text-white mb-2 flex items-center justify-end gap-2 text-sm">کاربران Windows (ویندوز) <span className="text-xl">💻</span></h3>
            <p className="text-xs text-gray-400 leading-relaxed">برنامه <b>v2rayN</b> یا <b>Nekobox</b> را دانلود و نصب کرده و لینک سابسکریپشن را در آن وارد نمایید.</p>
          </div>

          <div className="bg-slate-900/50 p-4 rounded-2xl border border-white/5">
            <h3 className="font-bold text-white mb-2 flex items-center justify-end gap-2 text-sm">کاربران macOS (مکینتاش) <span className="text-xl">🍎</span></h3>
            <p className="text-xs text-gray-400 leading-relaxed">از برنامه <b>V2Box</b> یا <b>FoXray</b> یا <b>V2rayU</b> برای مک استفاده کنید و لینک سابسکریپشن را ایمپورت کنید.</p>
          </div>
        </div>
        
        <div className="mt-6 pt-4 border-t border-white/10 text-center">
          <p className="text-xs text-indigo-300">در صورت نیاز به راهنمایی بیشتر با پشتیبانی در ارتباط باشید.</p>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-vazir pb-24 pt-4 px-4">
      {/* Decorative colored glow orbs */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-80 h-80 bg-indigo-900/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-10 right-10 w-64 h-64 bg-fuchsia-950/10 rounded-full blur-3xl pointer-events-none" />

      {/* Main Content Area */}
      <div className="relative z-10 w-full">
        {activeTab === 'dashboard' && renderDashboardTab()}
        {activeTab === 'shop' && renderShopTab()}
        {activeTab === 'wallet' && <PaymentSection />}
        {activeTab === 'support' && renderSupportTab()}
        {activeTab === 'tutorial' && renderTutorialTab()}
      </div>

      {/* Floating Glass Navigation Dock */}
      <div className="fixed bottom-4 left-4 right-4 bg-slate-950/65 backdrop-blur-2xl border border-white/10 px-4 py-2.5 rounded-3xl flex justify-between items-center z-50 shadow-2xl shadow-black/80 max-w-md mx-auto">
        <button 
          onClick={() => { setActiveTab('dashboard'); setSelectedTicket(null); }} 
          className={`flex flex-col items-center p-2 rounded-2xl transition-all duration-300 ${
            activeTab === 'dashboard' ? 'text-indigo-400 scale-105' : 'text-gray-400 hover:text-slate-200'
          }`}
        >
          <Home size={20} />
          <span className="text-[9px] font-bold mt-1">داشبورد</span>
          {activeTab === 'dashboard' && <span className="w-1 h-1 bg-indigo-400 rounded-full mt-0.5 animate-pulse" />}
        </button>

        <button 
          onClick={() => { setActiveTab('shop'); setSelectedTicket(null); }} 
          className={`flex flex-col items-center p-2 rounded-2xl transition-all duration-300 ${
            activeTab === 'shop' ? 'text-indigo-400 scale-105' : 'text-gray-400 hover:text-slate-200'
          }`}
        >
          <Server size={20} />
          <span className="text-[9px] font-bold mt-1">فروشگاه</span>
          {activeTab === 'shop' && <span className="w-1 h-1 bg-indigo-400 rounded-full mt-0.5 animate-pulse" />}
        </button>

        <button 
          onClick={() => { setActiveTab('wallet'); setSelectedTicket(null); }} 
          className={`flex flex-col items-center p-2 rounded-2xl transition-all duration-300 ${
            activeTab === 'wallet' ? 'text-indigo-400 scale-105' : 'text-gray-400 hover:text-slate-200'
          }`}
        >
          <CreditCard size={20} />
          <span className="text-[9px] font-bold mt-1">کیف پول</span>
          {activeTab === 'wallet' && <span className="w-1 h-1 bg-indigo-400 rounded-full mt-0.5 animate-pulse" />}
        </button>

        <button 
          onClick={() => { setActiveTab('tutorial'); setSelectedTicket(null); }} 
          className={`flex flex-col items-center p-2 rounded-2xl transition-all duration-300 ${
            activeTab === 'tutorial' ? 'text-indigo-400 scale-105' : 'text-gray-400 hover:text-slate-200'
          }`}
        >
          <BookOpen size={20} />
          <span className="text-[9px] font-bold mt-1">آموزش</span>
          {activeTab === 'tutorial' && <span className="w-1 h-1 bg-indigo-400 rounded-full mt-0.5 animate-pulse" />}
        </button>

        <button 
          onClick={() => { setActiveTab('support'); setSelectedTicket(null); }} 
          className={`flex flex-col items-center p-2 rounded-2xl transition-all duration-300 ${
            activeTab === 'support' ? 'text-indigo-400 scale-105' : 'text-gray-400 hover:text-slate-200'
          }`}
        >
          <LifeBuoy size={20} />
          <span className="text-[9px] font-bold mt-1">پشتیبانی</span>
          {activeTab === 'support' && <span className="w-1 h-1 bg-indigo-400 rounded-full mt-0.5 animate-pulse" />}
        </button>
      </div>
    </div>
  );
};

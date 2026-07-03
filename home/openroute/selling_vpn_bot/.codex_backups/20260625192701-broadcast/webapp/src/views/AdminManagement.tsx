import React, { useEffect, useState } from 'react';
import { CheckCircle, XCircle, Send, Users, Activity, DollarSign, Server, Plus, Power, PowerOff, ArrowLeft, RefreshCw, HardDrive, Search, ChevronRight, Megaphone } from 'lucide-react';
import { apiClient } from '../api/client';
import '../App.css';

const safeFormatDate = (dateStr: string | undefined | null): string => {
  if (!dateStr) return '---';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) {
      const parts = dateStr.split('T')[0].split('-');
      if (parts.length === 3) {
        const year = parseInt(parts[0], 10);
        const month = parseInt(parts[1], 10) - 1;
        const day = parseInt(parts[2], 10);
        const d2 = new Date(year, month, day);
        if (!isNaN(d2.getTime())) {
          return d2.toLocaleDateString('fa-IR');
        }
      }
      return dateStr.split('T')[0] || '---';
    }
    return d.toLocaleDateString('fa-IR');
  } catch (e) {
    return dateStr.split('T')[0] || '---';
  }
};

const safeFormatTime = (dateStr: string | undefined | null): string => {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) {
      const cleaned = dateStr.replace(' ', 'T');
      const d2 = new Date(cleaned);
      if (isNaN(d2.getTime())) {
        const tPart = dateStr.split('T')[1];
        if (tPart) {
          return tPart.substring(0, 5);
        }
        return '';
      }
      return d2.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return '';
  }
};


interface ServerData {
  id: number;
  name: string;
  ip_address: string;
  ssh_port: number;
  status: string;
  active_accounts: number;
}

interface UserAccount {
  id: number;
  username: string;
  status: string;
  traffic_used_gb: number;
  traffic_limit_gb: number | null;
  expires_at: string;
}

interface UserData {
  id: number;
  username: string | null;
  balance: number;
  accounts: UserAccount[];
}

interface PaymentRecord {
  id: number;
  user_id: number;
  username?: string | null;
  amount: number;
  payment_method?: string;
  card_last_four?: string | null;
  server_name: string;
  status: string;
  created_at?: string;
  retryable?: boolean;
  receipt_url?: string | null;
  receipt_is_doc?: boolean;
}

interface SupportTicket {
  id: number;
  user_id: number;
  subject: string;
  status: string;
  updated_at: string;
}

interface TicketMessage {
  id: number;
  sender: 'user' | 'admin';
  text: string;
  created_at: string;
}

export const AdminManagement: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'overview' | 'users' | 'payments' | 'tickets' | 'broadcast'>('overview');
  const [loading, setLoading] = useState(true);

  // Broadcast
  const [broadcastText, setBroadcastText] = useState('');
  const [isBroadcasting, setIsBroadcasting] = useState(false);

  // Stats & Servers
  const [stats, setStats] = useState<any>(null);
  const [servers, setServers] = useState<ServerData[]>([]);
  const [showAddServer, setShowAddServer] = useState(false);
  const [newServerName, setNewServerName] = useState('');
  const [newServerIp, setNewServerIp] = useState('');
  const [newServerPort, setNewServerPort] = useState('22');
  const [newServerPassword, setNewServerPassword] = useState('');
  const [addingServer, setAddingServer] = useState(false);

  // User Directory
  const [users, setUsers] = useState<UserData[]>([]);
  const [userSearch, setUserSearch] = useState('');
  const [userPage] = useState(1);
  const [loadingUsers, setLoadingUsers] = useState(false);

  // Payments
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [loadingPayments, setLoadingPayments] = useState(false);
  const [receiptModal, setReceiptModal] = useState<{ url: string; isDoc: boolean } | null>(null);

  // Tickets
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [selectedTicket, setSelectedTicket] = useState<SupportTicket | null>(null);
  const [ticketMessages, setTicketMessages] = useState<TicketMessage[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [replyText, setReplyText] = useState('');

  const fetchOverviewData = async () => {
    setLoading(true);
    try {
      const [statsRes, serversRes] = await Promise.all([
        apiClient.get('/admin/webapp/stats'),
        apiClient.get('/admin/webapp/servers')
      ]);
      setStats(statsRes.data);
      setServers(serversRes.data || []);
    } catch (err) {
      console.error("Error fetching overview data", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchUsers = async (searchStr = '', page = 1) => {
    setLoadingUsers(true);
    try {
      const res = await apiClient.get(`/admin/webapp/users?page=${page}&limit=20&search=${searchStr}`);
      setUsers(res.data.users || []);
    } catch (err) {
      console.error("Error fetching users", err);
    } finally {
      setLoadingUsers(false);
    }
  };

  const fetchPayments = async () => {
    setLoadingPayments(true);
    try {
      const res = await apiClient.get('/admin/webapp/payments');
      setPayments(res.data.payments || []);
    } catch (err) {
      console.error("Error fetching payments", err);
    } finally {
      setLoadingPayments(false);
    }
  };

  const fetchTickets = async () => {
    try {
      const res = await apiClient.get('/admin/webapp/tickets');
      setTickets(res.data.tickets || []);
    } catch (err) {
      console.error("Error fetching tickets", err);
    }
  };

  const fetchTicketMessages = async (ticketId: number) => {
    setLoadingMessages(true);
    try {
      const res = await apiClient.get(`/admin/webapp/tickets/${ticketId}/messages`);
      setTicketMessages(res.data.messages || []);
    } catch (err) {
      console.error("Error fetching messages", err);
    } finally {
      setLoadingMessages(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'overview') {
      fetchOverviewData();
    } else if (activeTab === 'users') {
      fetchUsers(userSearch, userPage);
    } else if (activeTab === 'payments') {
      fetchPayments();
    } else if (activeTab === 'tickets') {
      fetchTickets();
    }
  }, [activeTab]);

  const handleAddServer = async () => {
    if (!newServerName.trim() || !newServerIp.trim() || !newServerPassword.trim()) return;
    setAddingServer(true);
    try {
      await apiClient.post('/admin/webapp/servers', {
        name: newServerName,
        ip_address: newServerIp,
        ssh_port: parseInt(newServerPort) || 22,
        root_password: newServerPassword
      });
      setNewServerName('');
      setNewServerIp('');
      setNewServerPort('22');
      setNewServerPassword('');
      setShowAddServer(false);
      await fetchOverviewData();
      alert("سرور جدید با موفقیت ثبت گردید.");
    } catch (err) {
      alert("خطا در ایجاد سرور جدید.");
    } finally {
      setAddingServer(false);
    }
  };

  const handleToggleAccount = async (accountId: number, currentStatus: string) => {
    const action = currentStatus === 'active' ? 'lock' : 'unlock';
    try {
      await apiClient.post(`/admin/webapp/accounts/${accountId}/toggle`, { action });
      setUsers(prevUsers => 
        prevUsers.map(u => ({
          ...u,
          accounts: u.accounts.map(a => a.id === accountId ? { ...a, status: action === 'lock' ? 'locked' : 'active' } : a)
        }))
      );
      alert(action === 'lock' ? "ارتباط اکانت با موفقیت مسدود شد." : "اکانت با موفقیت فعال‌سازی شد.");
    } catch (err) {
      alert("خطا در تغییر وضعیت اکانت.");
    }
  };

  const handlePaymentAction = async (paymentId: number, action: 'approve' | 'decline' | 'retry') => {
    try {
      await apiClient.post(`/admin/webapp/payments/${paymentId}/${action}`);
      await fetchPayments();
      alert(action === 'retry' ? 'تلاش مجدد فعال‌سازی انجام شد.' : action === 'approve' ? 'تراکنش تایید شد.' : 'تراکنش رد شد.');
    } catch (err) {
      alert('خطا در ثبت وضعیت تراکنش.');
    }
  };

  const handleSendReply = async () => {
    if (!replyText.trim() || !selectedTicket) return;
    const currentReply = replyText;
    setReplyText('');
    try {
      await apiClient.post(`/admin/webapp/tickets/${selectedTicket.id}/reply`, {
        text: currentReply
      });
      await fetchTicketMessages(selectedTicket.id);
    } catch (err) {
      alert("خطا در ارسال پاسخ.");
      setReplyText(currentReply);
    }
  };

  const handleSendBroadcast = async () => {
    if (!broadcastText.trim()) return;
    setIsBroadcasting(true);
    try {
      await apiClient.post('/admin/webapp/broadcast', { message: broadcastText });
      setBroadcastText('');
      alert("پیام همگانی با موفقیت ارسال شد.");
    } catch (err) {
      alert("خطا در ارسال پیام همگانی.");
    } finally {
      setIsBroadcasting(false);
    }
  };

  const handleUserSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value;
    setUserSearch(query);
    fetchUsers(query, 1);
  };

  const formatPrice = (num: number) => {
    return num.toLocaleString('fa-IR') + ' تومان';
  };

  const getPaymentStatusLabel = (statusValue: string) => {
    if (statusValue === 'provisioning_failed') return 'نیازمند تلاش مجدد';
    if (statusValue === 'processing') return 'در حال پردازش';
    if (statusValue === 'pending') return 'در انتظار بررسی';
    return statusValue;
  };

  if (loading && activeTab === 'overview') {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 font-vazir flex flex-col items-center justify-center space-y-4">
        <div className="w-10 h-10 border-t-2 border-r-2 border-indigo-500 rounded-full animate-spin" />
        <span className="text-xs text-gray-400">در حال بارگذاری داشبورد مدیریت...</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-vazir pb-24 pt-4 px-4">
      {/* Receipt Fullscreen Modal */}
      {receiptModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm"
          onClick={() => setReceiptModal(null)}
        >
          <div className="relative max-w-full max-h-full p-4" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setReceiptModal(null)}
              className="absolute top-2 right-2 w-9 h-9 rounded-full bg-white/10 text-white flex items-center justify-center hover:bg-white/20 transition-all z-10"
            >
              <XCircle size={20} />
            </button>
            {receiptModal.isDoc ? (
              <div className="text-center text-white p-8">
                <p className="text-sm mb-4">این فایل به صورت سند ارسال شده است.</p>
                <a
                  href={receiptModal.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="bg-indigo-600 text-white px-6 py-3 rounded-xl text-sm font-bold hover:bg-indigo-700 transition-all"
                >
                  دانلود / مشاهده فایل
                </a>
              </div>
            ) : (
              <img
                src={receiptModal.url}
                alt="رسید پرداخت"
                className="max-w-[90vw] max-h-[85vh] rounded-2xl shadow-2xl object-contain"
              />
            )}
            <p className="text-center text-gray-400 text-xs mt-3">برای بستن روی خارج از تصویر کلیک کنید</p>
          </div>
        </div>
      )}
      <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-900/10 rounded-full blur-3xl pointer-events-none" />

      <div className="max-w-md mx-auto mb-6 flex justify-between items-center px-1">
        <div>
          <h1 className="text-xl font-black text-white flex items-center gap-2">
            <Activity className="text-indigo-400" size={20} />
            <span>مدیریت پلتفرم</span>
          </h1>
          <p className="text-[10px] text-gray-400 mt-0.5">داشبورد یکپارچه نظارت و کنترل</p>
        </div>
      </div>

      <div className="flex bg-slate-900/40 p-1 rounded-2xl border border-white/5 backdrop-blur-xl max-w-md mx-auto mb-6 overflow-x-auto">
        <button 
          onClick={() => { setActiveTab('overview'); setSelectedTicket(null); }}
          className={`flex-1 py-2 rounded-xl text-[10px] font-bold transition-all ${activeTab === 'overview' ? 'bg-gradient-premium text-white shadow-lg' : 'text-gray-400'}`}
        >
          نظارت کل
        </button>
        <button 
          onClick={() => { setActiveTab('users'); setSelectedTicket(null); }}
          className={`flex-1 py-2 rounded-xl text-[10px] font-bold transition-all ${activeTab === 'users' ? 'bg-gradient-premium text-white shadow-lg' : 'text-gray-400'}`}
        >
          کاربران
        </button>
        <button 
          onClick={() => { setActiveTab('payments'); setSelectedTicket(null); }}
          className={`flex-1 py-2 rounded-xl text-[10px] font-bold transition-all ${activeTab === 'payments' ? 'bg-gradient-premium text-white shadow-lg' : 'text-gray-400'}`}
        >
          تراکنش‌ها
        </button>
        <button 
          onClick={() => { setActiveTab('tickets'); setSelectedTicket(null); }}
          className={`flex-1 py-2 rounded-xl text-[10px] font-bold transition-all ${activeTab === 'tickets' ? 'bg-gradient-premium text-white shadow-lg' : 'text-gray-400'}`}
        >
          تیکت‌ها
        </button>
        <button 
          onClick={() => { setActiveTab('broadcast'); setSelectedTicket(null); }}
          className={`flex-1 py-2 rounded-xl text-[10px] font-bold transition-all ${activeTab === 'broadcast' ? 'bg-gradient-premium text-white shadow-lg' : 'text-gray-400'}`}
        >
          اعلان
        </button>
      </div>

      <div className="relative z-10 max-w-md mx-auto">
        
        {/* OVERVIEW & SERVERS */}
        {activeTab === 'overview' && (
          <div className="space-y-6 animate-fade-in">
            {/* Stats Cards */}
            <div className="grid grid-cols-2 gap-4">
              <div className="glass-panel p-4 rounded-2xl border border-white/10 flex items-center gap-3">
                <div className="w-10 h-10 bg-slate-900/60 text-indigo-400 rounded-xl flex items-center justify-center border border-white/5">
                  <Users size={18} />
                </div>
                <div>
                  <span className="block text-[9px] text-gray-400">کل کاربران</span>
                  <span className="text-base font-black text-white font-sans">{stats?.total_users || 0}</span>
                </div>
              </div>

              <div className="glass-panel p-4 rounded-2xl border border-white/10 flex items-center gap-3">
                <div className="w-10 h-10 bg-slate-900/60 text-indigo-400 rounded-xl flex items-center justify-center border border-white/5">
                  <HardDrive size={18} />
                </div>
                <div>
                  <span className="block text-[9px] text-gray-400">اکانت‌های فعال</span>
                  <span className="text-base font-black text-white font-sans">{stats?.active_ssh_accounts || 0}</span>
                </div>
              </div>

              <div className="glass-panel p-4 rounded-2xl border border-white/10 flex items-center gap-3">
                <div className="w-10 h-10 bg-slate-900/60 text-emerald-400 rounded-xl flex items-center justify-center border border-white/5">
                  <DollarSign size={18} />
                </div>
                <div>
                  <span className="block text-[9px] text-gray-400">کل درآمد ثبت شده</span>
                  <span className="text-sm font-black text-emerald-400 font-sans">{formatPrice(stats?.total_revenue || 0)}</span>
                </div>
              </div>

              <div className="glass-panel p-4 rounded-2xl border border-white/10 flex items-center gap-3">
                <div className="w-10 h-10 bg-slate-900/60 text-blue-400 rounded-xl flex items-center justify-center border border-white/5">
                  <Activity size={18} />
                </div>
                <div>
                  <span className="block text-[9px] text-gray-400">ترافیک مصرفی کل</span>
                  <span className="text-base font-black text-blue-400 font-sans">{stats?.total_bandwidth_gb || 0} GB</span>
                </div>
              </div>
            </div>

            {/* Servers List */}
            <div className="space-y-4">
              <div className="flex justify-between items-center px-1">
                <h3 className="text-sm font-extrabold text-white">سرورهای متصل</h3>
                <button 
                  onClick={() => setShowAddServer(!showAddServer)}
                  className="bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-3 py-1 rounded-xl text-[10px] font-bold flex items-center gap-1 active:scale-95 transition-all"
                >
                  <Plus size={12} /> افزودن سرور جدید
                </button>
              </div>

              {/* Add Server Form */}
              {showAddServer && (
                <div className="glass-panel p-4 rounded-2xl border border-indigo-500/30 space-y-3 animate-slide-up">
                  <h4 className="text-xs font-bold text-indigo-300">مشخصات سرور لینوکس جدید</h4>
                  <div className="grid grid-cols-2 gap-2">
                    <input 
                      type="text" 
                      placeholder="نام سرور (مثال: انگلستان)" 
                      value={newServerName}
                      onChange={(e) => setNewServerName(e.target.value)}
                      className="bg-slate-950/60 border border-white/5 rounded-xl px-3 py-2 text-[10px] text-white focus:outline-none focus:border-indigo-500"
                    />
                    <input 
                      type="text" 
                      placeholder="آی‌پی سرور" 
                      value={newServerIp}
                      onChange={(e) => setNewServerIp(e.target.value)}
                      className="bg-slate-950/60 border border-white/5 rounded-xl px-3 py-2 text-[10px] text-white focus:outline-none focus:border-indigo-500 font-mono text-left"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <input 
                      type="text" 
                      placeholder="پورت SSH (پیش‌فرض: 22)" 
                      value={newServerPort}
                      onChange={(e) => setNewServerPort(e.target.value)}
                      className="bg-slate-950/60 border border-white/5 rounded-xl px-3 py-2 text-[10px] text-white focus:outline-none focus:border-indigo-500 font-mono text-left"
                    />
                    <input 
                      type="password" 
                      placeholder="رمز عبور روت سرور" 
                      value={newServerPassword}
                      onChange={(e) => setNewServerPassword(e.target.value)}
                      className="bg-slate-950/60 border border-white/5 rounded-xl px-3 py-2 text-[10px] text-white focus:outline-none focus:border-indigo-500 font-mono text-left"
                    />
                  </div>
                  <button 
                    onClick={handleAddServer}
                    disabled={addingServer}
                    className="w-full bg-gradient-premium text-white py-2 rounded-xl text-[10px] font-bold shadow-md active:scale-95 transition-all flex justify-center items-center gap-1"
                  >
                    {addingServer ? <RefreshCw className="animate-spin" size={12} /> : null}
                    اتصال و ذخیره سرور
                  </button>
                </div>
              )}

              {servers.map(srv => {
                const isOnline = srv.status === 'Online';
                return (
                  <div key={srv.id} className="glass-panel p-4 rounded-2xl border border-white/10 flex justify-between items-center hover:border-white/20 transition-all">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 bg-slate-900/60 text-indigo-400 rounded-xl flex items-center justify-center border border-white/5">
                        <Server size={18} />
                      </div>
                      <div>
                        <h4 className="font-extrabold text-xs text-white">{srv.name}</h4>
                        <span className="block text-[8px] text-gray-500 font-mono mt-0.5">{srv.ip_address}:{srv.ssh_port}</span>
                      </div>
                    </div>

                    <div className="text-left space-y-1">
                      <span className={`text-[8px] font-bold px-2 py-0.5 rounded-full ${isOnline ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'}`}>
                        {isOnline ? 'روشن (Online)' : 'خاموش (Offline)'}
                      </span>
                      <span className="block text-[8px] text-gray-400 mt-1">اکانت‌ها: {srv.active_accounts}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* USER DIRECTORY */}
        {activeTab === 'users' && (
          <div className="space-y-4 animate-fade-in">
            {/* Search Input */}
            <div className="bg-slate-900/50 p-2.5 rounded-2xl border border-white/5 flex items-center backdrop-blur-xl">
              <Search size={14} className="text-gray-500 mr-2" />
              <input 
                type="text"
                placeholder="جستجوی نام کاربری..."
                value={userSearch}
                onChange={handleUserSearchChange}
                className="flex-grow bg-transparent text-xs text-white focus:outline-none placeholder-gray-500"
              />
              {loadingUsers ? <RefreshCw className="animate-spin text-indigo-400" size={12} /> : null}
            </div>

            {/* Users list */}
            <div className="space-y-3">
              {users.length === 0 ? (
                <div className="text-center text-xs text-gray-500 py-10">کاربری یافت نشد.</div>
              ) : (
                users.map(u => (
                  <div key={u.id} className="glass-panel rounded-2xl border border-white/10 overflow-hidden">
                    <div className="p-3 bg-white/5 font-extrabold text-xs flex justify-between border-b border-white/5">
                      <span className="text-indigo-300 font-mono">@{u.username || `User_${u.id}`}</span>
                      <span className="text-gray-400">موجودی: <strong className="text-emerald-400 font-sans">{formatPrice(u.balance)}</strong></span>
                    </div>

                    {u.accounts.length === 0 ? (
                      <div className="p-4 text-center text-[10px] text-gray-500">اکانت فعال ندارد</div>
                    ) : (
                      <div className="p-3 space-y-3">
                        {u.accounts.map(acc => {
                          const isActive = acc.status === 'active';
                          return (
                            <div key={acc.id} className="flex justify-between items-center text-[11px]">
                              <div>
                                <span className="font-mono text-white font-bold">{acc.username}</span>
                                <span className="block text-[8px] text-gray-500 mt-0.5">
                                  مصرف: {acc.traffic_used_gb.toFixed(1)} / {acc.traffic_limit_gb || '∞'} GB
                                </span>
                              </div>

                              <button 
                                onClick={() => handleToggleAccount(acc.id, acc.status)}
                                className={`px-3 py-1 rounded-xl text-[9px] font-bold flex items-center gap-1 active:scale-95 transition-all ${
                                  isActive 
                                    ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20' 
                                    : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20'
                                }`}
                              >
                                {isActive ? (
                                  <><PowerOff size={10} /> قطع اتصال</>
                                ) : (
                                  <><Power size={10} /> فعالسازی</>
                                )}
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* PAYMENTS QUEUE */}
        {activeTab === 'payments' && (
          <div className="space-y-4 animate-fade-in">
            {loadingPayments ? (
              <div className="text-center py-10">
                <RefreshCw className="animate-spin text-indigo-400" size={16} />
              </div>
            ) : payments.length === 0 ? (
              <div className="text-center text-xs text-gray-500 py-10">تراکنش قابل بررسی یا بازیابی وجود ندارد.</div>
            ) : (
              payments.map(p => (
                <div key={p.id} className="glass-panel p-4 rounded-2xl border border-white/10 space-y-3">
                  <div className="flex justify-between items-start">
                    <div>
                      <h4 className="font-extrabold text-sm text-emerald-400 font-sans">{formatPrice(p.amount)}</h4>
                      <span className="block text-[8px] text-gray-500 mt-0.5">
                        کاربر: @{p.username || p.user_id} • طرح: {p.server_name}
                      </span>
                    </div>
                    <span className={`text-[8px] font-extrabold px-2 py-0.5 rounded-full border ${
                      p.status === 'provisioning_failed'
                        ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                        : p.status === 'processing'
                          ? 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                          : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                    }`}>
                      {getPaymentStatusLabel(p.status)}
                    </span>
                  </div>

                  <div className="bg-slate-950/40 p-2.5 rounded-xl border border-white/5 text-[10px] space-y-1">
                    <div className="flex justify-between">
                      <span className="text-gray-500">روش پرداخت:</span>
                      <span className="font-mono text-white font-bold">{p.payment_method === 'crypto' ? 'Crypto' : 'Card'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">۴ رقم آخر کارت:</span>
                      <span className="font-mono text-white font-bold">{p.card_last_four || '-'}</span>
                    </div>
                  </div>

                  {/* Payment Receipt Screenshot */}
                  {p.receipt_url && (
                    <div
                      className="relative cursor-pointer group rounded-xl overflow-hidden border border-white/10 hover:border-indigo-500/40 transition-all"
                      onClick={() => setReceiptModal({ url: p.receipt_url!, isDoc: p.receipt_is_doc ?? false })}
                    >
                      {p.receipt_is_doc ? (
                        <div className="bg-slate-900/60 p-3 flex items-center gap-3 text-[11px] text-indigo-300 font-bold">
                          <div className="w-8 h-8 rounded-lg bg-indigo-500/15 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                          </div>
                          <span>رسید پرداخت (فایل) — برای مشاهده کلیک کنید</span>
                        </div>
                      ) : (
                        <div className="relative">
                          <img
                            src={p.receipt_url}
                            alt="رسید پرداخت"
                            className="w-full h-36 object-cover"
                          />
                          <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-all flex items-end justify-center pb-2">
                            <span className="text-white text-[10px] font-bold">برای بزرگنمایی کلیک کنید</span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="flex gap-2">
                    {p.retryable ? (
                      <button
                        onClick={() => handlePaymentAction(p.id, 'retry')}
                        className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 rounded-xl text-[10px] flex items-center justify-center gap-1 shadow-md active:scale-95 transition-all"
                      >
                        <RefreshCw size={12} /> تلاش مجدد فعال‌سازی
                      </button>
                    ) : (
                      <>
                        <button 
                          onClick={() => handlePaymentAction(p.id, 'approve')}
                          disabled={p.status !== 'pending'}
                          className="flex-1 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-700 disabled:text-gray-400 text-white font-bold py-2 rounded-xl text-[10px] flex items-center justify-center gap-1 shadow-md active:scale-95 transition-all"
                        >
                          <CheckCircle size={12} /> تایید و شارژ
                        </button>
                        <button 
                          onClick={() => handlePaymentAction(p.id, 'decline')}
                          disabled={p.status === 'processing'}
                          className="flex-1 bg-rose-600 hover:bg-rose-700 disabled:bg-slate-700 disabled:text-gray-400 text-white font-bold py-2 rounded-xl text-[10px] flex items-center justify-center gap-1 shadow-md active:scale-95 transition-all"
                        >
                          <XCircle size={12} /> رد درخواست
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* SUPPORT TICKETS INBOX */}
        {activeTab === 'tickets' && (
          <div className="space-y-4 animate-fade-in">
            {selectedTicket ? (
              <div className="flex flex-col h-[calc(100vh-200px)] animate-fade-in">
                {/* Detail Header */}
                <div className="flex justify-between items-center pb-3 border-b border-white/5 mb-3">
                  <div className="flex items-center gap-2">
                    <button 
                      onClick={() => { setSelectedTicket(null); setTicketMessages([]); }} 
                      className="w-8 h-8 rounded-xl bg-white/5 border border-white/5 text-gray-300 flex items-center justify-center hover:bg-white/10 active:scale-90 transition-all"
                    >
                      <ArrowLeft size={16} />
                    </button>
                    <div>
                      <h4 className="font-extrabold text-xs text-white truncate max-w-[180px]">{selectedTicket.subject}</h4>
                      <span className="text-[8px] text-gray-500">کاربر: #{selectedTicket.user_id}</span>
                    </div>
                  </div>
                  <span className={`text-[8px] font-extrabold px-2 py-0.5 rounded-full border ${
                    selectedTicket.status === 'open' 
                      ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' 
                      : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  }`}>
                    {selectedTicket.status === 'open' ? 'درحال بررسی' : 'پاسخ داده شده'}
                  </span>
                </div>

                {/* Messages Panel */}
                <div className="flex-1 overflow-y-auto space-y-3 custom-scrollbar mb-3 pr-1 pl-1">
                  {loadingMessages ? (
                    <div className="flex justify-center items-center py-10">
                      <RefreshCw className="animate-spin text-indigo-400" size={16} />
                    </div>
                  ) : (
                    ticketMessages.map(m => {
                      const isAdminMsg = m.sender === 'admin';
                      return (
                        <div key={m.id} className={`flex flex-col ${isAdminMsg ? 'items-end' : 'items-start'}`}>
                          <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-xs shadow-sm ${
                            isAdminMsg 
                              ? 'bg-indigo-600 text-white rounded-tr-sm shadow-indigo-600/5' 
                              : 'bg-slate-800 text-slate-100 rounded-tl-sm border border-white/5'
                          }`}>
                            <p className="leading-relaxed whitespace-pre-wrap">{m.text}</p>
                          </div>
                          <span className="text-[8px] text-gray-500 mt-1 font-mono">
                            {safeFormatTime(m.created_at)}
                          </span>
                        </div>
                      );
                    })
                  )}
                </div>

                {/* Message Entry form */}
                <div className="bg-slate-900/50 p-2.5 rounded-2xl border border-white/5 flex items-center backdrop-blur-xl">
                  <input 
                    type="text" 
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    placeholder="پاسخ مدیریت..."
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
            ) : (
              <div className="space-y-3">
                {tickets.length === 0 ? (
                  <div className="glass-panel text-center py-10 px-6 rounded-3xl border border-white/5 text-xs text-gray-400">
                    تیکت بازی یافت نشد.
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
                          <span>تیکت #{t.id} • کاربر: #{t.user_id}</span>
                          <span>•</span>
                          <span>{safeFormatDate(t.updated_at)}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className={`text-[8px] font-extrabold px-2 py-0.5 rounded-full border ${
                          t.status === 'open' 
                            ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' 
                            : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                        }`}>
                          {t.status === 'open' ? 'جدید / باز' : 'پاسخ داده شده'}
                        </span>
                        <ChevronRight size={14} className="text-gray-500" />
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === 'broadcast' && (
          <div className="space-y-6 animate-fade-in relative z-10">
            <div className="glass-panel p-6 rounded-3xl border border-indigo-500/20 shadow-xl text-right">
              <h2 className="text-xl font-extrabold text-white mb-2 flex items-center justify-end gap-2">
                ارسال پیام همگانی <Megaphone className="text-indigo-400" size={24} />
              </h2>
              <p className="text-gray-400 text-xs mb-6 leading-relaxed">
                پیام خود را در کادر زیر وارد کنید تا برای تمامی کاربران ربات ارسال شود. این عملیات در پس‌زمینه انجام می‌شود و ممکن است دقایقی طول بکشد.
              </p>
              <textarea
                value={broadcastText}
                onChange={(e) => setBroadcastText(e.target.value)}
                placeholder="متن پیام خود را اینجا بنویسید..."
                className="w-full h-32 bg-slate-900/60 border border-white/10 rounded-2xl px-4 py-3 text-right text-sm text-white focus:outline-none focus:border-indigo-500 transition-all mb-4"
                dir="rtl"
              />
              <button
                onClick={handleSendBroadcast}
                disabled={!broadcastText.trim() || isBroadcasting}
                className={`w-full font-bold py-3.5 rounded-2xl text-sm flex justify-center items-center transition-all duration-300 ${
                  broadcastText.trim() && !isBroadcasting
                    ? 'bg-gradient-premium text-white shadow-lg shadow-indigo-600/30'
                    : 'bg-slate-800 text-gray-500 cursor-not-allowed border border-white/5'
                }`}
              >
                {isBroadcasting ? (
                  <>
                    <RefreshCw className="animate-spin ml-2" size={16} /> در حال ارسال...
                  </>
                ) : (
                  <>
                    <Send className="ml-2" size={16} /> ارسال پیام همگانی
                  </>
                )}
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};

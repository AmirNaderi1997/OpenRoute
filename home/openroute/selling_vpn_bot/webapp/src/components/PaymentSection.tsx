import React, { useState } from 'react';
import { AlertCircle, CheckCircle, Check, Copy, CreditCard, RefreshCw, Bitcoin } from 'lucide-react';
import { apiClient } from '../api/client';
import '../App.css';

export const PaymentSection: React.FC = () => {
  const [method, setMethod] = useState<'card' | 'crypto' | null>(null);
  const [amount, setAmount] = useState('');
  const [discountCode, setDiscountCode] = useState('');
  const [discountApplied, setDiscountApplied] = useState(false);
  const [discountPercent, setDiscountPercent] = useState<number | null>(null);
  const [payableToman, setPayableToman] = useState<number | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [copied, setCopied] = useState(false);

  const systemCard = '5859831130851222';
  const systemName = 'امیرحسین نادری';

  const resetState = (nextMethod: 'card' | 'crypto') => {
    setMethod(nextMethod);
    setAmount('');
    setDiscountCode('');
    setDiscountApplied(false);
    setDiscountPercent(null);
    setPayableToman(null);
    setSelectedFile(null);
    setStatus('idle');
    setErrorMsg('');
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(systemCard);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const applyDiscount = async () => {
    if (!discountCode.trim()) {
      setStatus('error');
      setErrorMsg('ابتدا کد تخفیف را وارد کنید.');
      return;
    }
    if (!amount) {
      setStatus('error');
      setErrorMsg('ابتدا مبلغ را وارد کنید.');
      return;
    }

    try {
      const payload = { amount: parseInt(amount, 10), discount_code: discountCode, payment_method: 'card' };
      const response = await apiClient.post('/webapp/payments/discount/preview', payload);
      setDiscountApplied(true);
      setDiscountPercent(response.data?.percent_off ?? null);
      setPayableToman(response.data?.payable_toman ?? null);
      setStatus('idle');
      setErrorMsg('');
    } catch (err: any) {
      setDiscountApplied(false);
      setDiscountPercent(null);
      setPayableToman(null);
      setStatus('error');
      const detail = err.response?.data?.detail;
      setErrorMsg(typeof detail === 'object' ? JSON.stringify(detail) : detail || 'کد تخفیف معتبر نیست.');
    }
  };

  const handleCardSubmit = async () => {
    const numericAmount = parseInt(amount, 10);
    if (Number.isNaN(numericAmount) || numericAmount <= 0) {
      setStatus('error');
      setErrorMsg('لطفاً مبلغ معتبری به تومان وارد کنید.');
      return;
    }
    if (!selectedFile) {
      setStatus('error');
      setErrorMsg('لطفاً فقط تصویر اسکرین‌شات رسید پرداخت را انتخاب کنید.');
      return;
    }

    setLoading(true);
    setStatus('idle');

    const formData = new FormData();
    formData.append('amount', numericAmount.toString());
    if (discountCode.trim()) {
      formData.append('discount_code', discountCode.trim());
    }
    formData.append('file', selectedFile);

    try {
      await apiClient.post('/webapp/payments/charge', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      setStatus('success');
      setAmount('');
      setSelectedFile(null);
    } catch (err: any) {
      setStatus('error');
      const detail = err.response?.data?.detail;
      setErrorMsg(typeof detail === 'object' ? JSON.stringify(detail) : detail || 'خطا در ثبت پرداخت. لطفا مجددا تلاش کنید.');
    } finally {
      setLoading(false);
    }
  };

  const handleCryptoSubmit = async () => {
    const numericAmount = parseInt(amount, 10);
    if (Number.isNaN(numericAmount) || numericAmount <= 0) {
      setStatus('error');
      setErrorMsg('لطفاً مبلغ معتبری به تومان وارد کنید.');
      return;
    }

    setLoading(true);
    setStatus('idle');

    try {
      const response = await apiClient.post('/webapp/payments/charge/crypto', {
        amount: numericAmount
      });
      if (response.data?.url) {
        window.location.href = response.data.url;
      } else {
        setStatus('error');
        setErrorMsg('لینک پرداخت دریافت نشد.');
      }
    } catch (err: any) {
      setStatus('error');
      const detail = err.response?.data?.detail;
      setErrorMsg(typeof detail === 'object' ? JSON.stringify(detail) : detail || 'خطا در ایجاد فاکتور پرداخت ارزی.');
    } finally {
      setLoading(false);
    }
  };

  const formatCardNumber = (num: string) => num.replace(/(\d{4})/g, '$1 ').trim();

  return (
    <div className="font-vazir space-y-6 max-w-md mx-auto">
      <div className="text-center">
        <h2 className="text-xl font-extrabold text-gradient-purple">افزایش موجودی کیف پول</h2>
        <p className="text-xs text-gray-400 mt-1">ابتدا روش پرداخت را انتخاب کنید</p>
      </div>

      <div className="flex bg-slate-900/40 p-1 rounded-2xl border border-white/5 backdrop-blur-xl gap-2">
        <button
          onClick={() => resetState('card')}
          className={`flex-1 flex items-center justify-center py-2.5 rounded-xl text-xs font-bold transition-all duration-300 ${
            method === 'card'
              ? 'bg-gradient-premium text-white shadow-lg shadow-indigo-600/30'
              : 'text-gray-400 hover:text-white hover:bg-white/5'
          }`}
        >
          <CreditCard size={15} className="ml-2" /> کارت به کارت
        </button>
        <button
          onClick={() => resetState('crypto')}
          className={`flex-1 flex items-center justify-center py-2.5 rounded-xl text-xs font-bold transition-all duration-300 ${
            method === 'crypto'
              ? 'bg-gradient-premium text-white shadow-lg shadow-indigo-600/30'
              : 'text-gray-400 hover:text-white hover:bg-white/5'
          }`}
        >
          <Bitcoin size={15} className="ml-2" /> ارزی (تتر/ترون)
        </button>
      </div>

      <div className="glass-panel p-6 rounded-3xl border border-white/10 shadow-2xl relative overflow-hidden animate-slide-up">
        {!method ? (
          <div className="text-center py-10 space-y-3">
            <div className="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center mx-auto border border-white/10">
              <CreditCard size={28} className="text-indigo-400" />
            </div>
            <h3 className="font-extrabold text-base text-white">روش پرداخت را انتخاب کنید</h3>
            <p className="text-xs text-gray-400 leading-relaxed px-4">
              تا قبل از انتخاب روش پرداخت، هیچ مبلغی نمایش داده نمی‌شود.
            </p>
          </div>
        ) : method === 'card' ? (
          <div className="space-y-6">
            <div
              onClick={handleCopy}
              className="relative aspect-[1.586/1] w-full rounded-2xl p-5 text-white bg-gradient-to-br from-slate-800 via-indigo-950 to-slate-950 shadow-2xl border border-white/10 flex flex-col justify-between overflow-hidden cursor-pointer group active:scale-95 transition-transform duration-200"
            >
              <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-white/5 to-white/10 pointer-events-none" />
              <div className="flex justify-between items-start z-10">
                <span className="text-[10px] tracking-widest text-indigo-300 font-medium">SHETAB DEBIT CARD</span>
                <span className="text-xs font-bold text-gray-300">بانک تجارت</span>
              </div>
              <div className="flex justify-between items-center z-10">
                <div className="w-9 h-7 bg-gradient-to-br from-amber-200 to-yellow-500 rounded-md opacity-80 flex flex-col justify-between p-1">
                  <div className="border-b border-black/20 h-1" />
                  <div className="border-b border-black/20 h-1" />
                  <div className="border-b border-black/20 h-1" />
                </div>
              </div>
              <div dir="ltr" className="text-center font-mono text-lg tracking-wider font-semibold z-10 text-slate-100 group-hover:text-indigo-300 transition-colors py-1">
                {formatCardNumber(systemCard)}
              </div>
              <div className="flex justify-between items-end z-10">
                <div>
                  <span className="block text-[8px] text-indigo-300 uppercase">صاحب کارت</span>
                  <span className="text-xs font-bold text-slate-200">{systemName}</span>
                </div>
                <div className="bg-white/10 px-2 py-1 rounded-md text-[9px] flex items-center gap-1 border border-white/5">
                  {copied ? (
                    <>
                      <Check size={10} className="text-green-400" />
                      کپی شد
                    </>
                  ) : (
                    <>
                      <Copy size={10} />
                      کلیک برای کپی
                    </>
                  )}
                </div>
              </div>
            </div>

            <p className="text-[11px] text-gray-400 text-center leading-relaxed px-2">
              مبلغ مورد نظر خود را به تومان وارد کنید، پرداخت را انجام دهید و سپس تصویر رسید را ارسال کنید.
            </p>

            <div className="space-y-4 pt-2 text-right" dir="rtl">
              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-indigo-300">مبلغ شارژ (تومان)</label>
                <input
                  type="text"
                  value={amount}
                  onChange={(e) => {
                    setAmount(e.target.value.replace(/\D/g, ''));
                    setDiscountApplied(false);
                    setPayableToman(null);
                  }}
                  placeholder="مثال: 600000"
                  className="w-full bg-slate-950/60 border border-white/10 rounded-2xl px-4 py-3 text-center font-bold text-white focus:outline-none focus:border-indigo-500 transition-all text-lg"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-indigo-300">کد تخفیف</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={discountCode}
                    onChange={(e) => {
                      setDiscountCode(e.target.value.toUpperCase());
                      setDiscountApplied(false);
                      setPayableToman(null);
                    }}
                    placeholder="اختیاری"
                    className="flex-1 bg-slate-950/60 border border-white/10 rounded-2xl px-4 py-3 text-center font-bold text-white focus:outline-none focus:border-indigo-500 transition-all"
                  />
                  <button
                    onClick={applyDiscount}
                    type="button"
                    className="px-4 py-3 rounded-2xl text-xs font-bold bg-white/5 border border-white/10 text-white"
                  >
                    اعمال
                  </button>
                </div>
              </div>

              {discountApplied && payableToman !== null && (
                <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-2xl p-3 text-xs text-emerald-300">
                  مبلغ قابل پرداخت با {discountPercent}% تخفیف: <strong>{payableToman.toLocaleString('fa-IR')} تومان</strong>
                </div>
              )}

              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-indigo-300">تصویر رسید پرداخت (اسکرین‌شات)</label>
                <div className="flex items-center justify-center w-full">
                  <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-2xl cursor-pointer hover:bg-slate-900/30 border-white/10 hover:border-indigo-500/50 transition-colors">
                    <div className="flex flex-col items-center justify-center pt-5 pb-6">
                      <p className="text-[10px] text-gray-400 text-center px-4 truncate max-w-full">
                        {selectedFile ? (
                          <span className="text-indigo-400 font-bold">{selectedFile.name}</span>
                        ) : (
                          <span>فقط تصویر اسکرین‌شات (jpg, png, webp) — کلیک کنید</span>
                        )}
                      </p>
                    </div>
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
                          setSelectedFile(file);
                        }
                      }}
                    />
                  </label>
                </div>
              </div>
            </div>

            {status === 'success' && (
              <div className="bg-emerald-500/10 text-emerald-400 p-3.5 rounded-2xl text-xs flex flex-col items-start gap-1.5 border border-emerald-500/20 animate-fade-in">
                <div className="flex items-center">
                  <CheckCircle size={15} className="ml-2.5 shrink-0" />
                  <span className="font-bold">ثبت با موفقیت انجام شد</span>
                </div>
                <p className="text-[11px] leading-relaxed text-emerald-300/95 text-right w-full" dir="rtl">
                  رسید پرداخت شما ارسال شد و پس از تایید مدیریت، کیف پول شما شارژ خواهد شد.
                </p>
              </div>
            )}

            {status === 'error' && (
              <div className="bg-rose-500/10 text-rose-400 p-3.5 rounded-2xl text-xs flex items-center border border-rose-500/20 animate-fade-in">
                <AlertCircle size={15} className="ml-2.5 shrink-0" />
                <span className="leading-relaxed">{errorMsg}</span>
              </div>
            )}

            <button
              onClick={handleCardSubmit}
              disabled={!amount || !selectedFile || loading}
              className={`w-full font-bold py-3.5 rounded-2xl text-sm flex justify-center items-center transition-all duration-300 ${
                amount && selectedFile && !loading
                  ? 'bg-gradient-premium text-white shadow-lg shadow-indigo-600/30 active:scale-[0.98]'
                  : 'bg-slate-800 text-gray-500 cursor-not-allowed border border-white/5'
              }`}
            >
              {loading ? (
                <>
                  <RefreshCw className="animate-spin ml-2" size={16} />
                  در حال ثبت پرداخت...
                </>
              ) : 'ثبت و ارسال رسید'}
            </button>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="text-center py-6">
              <div className="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center mx-auto border border-white/10 mb-4">
                <Bitcoin size={32} className="text-yellow-500" />
              </div>
              <h3 className="font-extrabold text-base text-white">پرداخت ارزی با NOWPayments</h3>
              <p className="text-xs text-gray-400 leading-relaxed px-4 mt-2">
                مبلغ مورد نظر به تومان را وارد کنید. سیستم معادل دلاری آن را برای پرداخت محاسبه خواهد کرد.
              </p>
            </div>

            <div className="space-y-4 pt-2 text-right" dir="rtl">
              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-indigo-300">مبلغ شارژ (تومان)</label>
                <input
                  type="text"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value.replace(/\D/g, ''))}
                  placeholder="مثال: 600000"
                  className="w-full bg-slate-950/60 border border-white/10 rounded-2xl px-4 py-3 text-center font-bold text-white focus:outline-none focus:border-indigo-500 transition-all text-lg"
                />
              </div>
            </div>

            {status === 'error' && (
              <div className="bg-rose-500/10 text-rose-400 p-3.5 rounded-2xl text-xs flex items-center border border-rose-500/20 animate-fade-in">
                <AlertCircle size={15} className="ml-2.5 shrink-0" />
                <span className="leading-relaxed">{errorMsg}</span>
              </div>
            )}

            <button
              onClick={handleCryptoSubmit}
              disabled={!amount || loading}
              className={`w-full font-bold py-3.5 rounded-2xl text-sm flex justify-center items-center transition-all duration-300 ${
                amount && !loading
                  ? 'bg-gradient-premium text-white shadow-lg shadow-indigo-600/30 active:scale-[0.98]'
                  : 'bg-slate-800 text-gray-500 cursor-not-allowed border border-white/5'
              }`}
            >
              {loading ? (
                <>
                  <RefreshCw className="animate-spin ml-2" size={16} />
                  در حال انتقال به درگاه...
                </>
              ) : 'پرداخت و انتقال به درگاه ارزی'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

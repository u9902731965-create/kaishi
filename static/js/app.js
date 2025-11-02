// 账单查询系统 - 前端逻辑

// 格式化数字
function formatNumber(num) {
    return num.toLocaleString('zh-CN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

// 格式化交易类型
function formatType(type) {
    const types = {
        'deposit': '<span class="badge badge-type-deposit">入金</span>',
        'withdrawal': '<span class="badge badge-type-withdrawal">出金</span>',
        'disbursement': '<span class="badge badge-type-disbursement">下发</span>'
    };
    return types[type] || type;
}

// 加载交易数据
function loadTransactions() {
    const formData = new FormData(document.getElementById('filterForm'));
    const params = new URLSearchParams(formData);
    
    fetch(`/api/transactions?${params.toString()}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateStatistics(data.statistics);
                renderTransactions(data.records);
                renderOperatorStats(data.statistics.by_operator);
            } else {
                alert('加载数据失败');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('加载数据失败');
        });
}

// 更新统计信息
function updateStatistics(stats) {
    document.getElementById('totalDeposit').textContent = formatNumber(stats.total_deposit);
    document.getElementById('totalDepositUSDT').textContent = formatNumber(stats.total_deposit_usdt) + ' USDT';
    
    document.getElementById('totalWithdrawal').textContent = formatNumber(stats.total_withdrawal);
    document.getElementById('totalWithdrawalUSDT').textContent = formatNumber(stats.total_withdrawal_usdt) + ' USDT';
    
    document.getElementById('totalDisbursement').textContent = formatNumber(stats.total_disbursement) + ' USDT';
    document.getElementById('pendingDisbursement').textContent = formatNumber(stats.pending_disbursement) + ' USDT';
}

// 渲染交易记录
function renderTransactions(records) {
    const tbody = document.getElementById('transactionTable');
    document.getElementById('recordCount').textContent = `${records.length} 条记录`;
    
    if (records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${IS_OWNER ? 8 : 7}" class="text-center text-muted">暂无记录</td></tr>`;
        return;
    }
    
    let html = '';
    records.forEach(record => {
        html += `
            <tr>
                <td>${record.time}</td>
                <td>${formatType(record.type)}</td>
                <td class="${record.type === 'deposit' ? 'text-success' : record.type === 'withdrawal' ? 'text-danger' : 'text-info'}">
                    ${formatNumber(record.amount)}
                </td>
                <td>${record.fee_rate > 0 ? record.fee_rate + '%' : '-'}</td>
                <td>${record.exchange_rate > 0 ? record.exchange_rate : '-'}</td>
                <td><strong>${formatNumber(record.usdt)}</strong></td>
                <td>
                    <span class="badge bg-secondary">${record.operator}</span>
                </td>
                ${IS_OWNER ? `
                    <td>
                        ${record.message_id ? `
                            <button class="btn btn-sm btn-danger btn-rollback" 
                                    onclick="showRollbackModal('${record.type}', ${record.message_id}, '${record.time}', ${record.usdt})">
                                <i class="bi bi-arrow-counterclockwise"></i> 回退
                            </button>
                        ` : '-'}
                    </td>
                ` : ''}
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

// 渲染操作员统计
function renderOperatorStats(byOperator) {
    const tbody = document.getElementById('operatorTable');
    
    if (Object.keys(byOperator).length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">暂无数据</td></tr>';
        return;
    }
    
    let html = '';
    Object.entries(byOperator).forEach(([operator, stats]) => {
        html += `
            <tr>
                <td><span class="badge bg-secondary">${operator}</span></td>
                <td>${stats.deposit_count}</td>
                <td class="text-success">${formatNumber(stats.deposit_usdt)}</td>
                <td>${stats.withdrawal_count}</td>
                <td class="text-danger">${formatNumber(stats.withdrawal_usdt)}</td>
                <td>${stats.disbursement_count}</td>
                <td class="text-info">${formatNumber(stats.disbursement_usdt)}</td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

// 显示回退确认对话框
function showRollbackModal(type, messageId, time, usdt) {
    currentRollbackData = { type, message_id: messageId };
    
    const typeText = {
        'deposit': '入金',
        'withdrawal': '出金',
        'disbursement': '下发'
    };
    
    document.getElementById('rollbackInfo').innerHTML = `
        <p><strong>交易类型:</strong> ${typeText[type]}</p>
        <p><strong>交易时间:</strong> ${time}</p>
        <p><strong>USDT金额:</strong> ${usdt}</p>
    `;
    
    const modal = new bootstrap.Modal(document.getElementById('rollbackModal'));
    modal.show();
}

// 确认回退
document.getElementById('confirmRollback').addEventListener('click', function() {
    if (!currentRollbackData) return;
    
    fetch('/api/rollback', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(currentRollbackData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('回退成功！');
            bootstrap.Modal.getInstance(document.getElementById('rollbackModal')).hide();
            loadTransactions(); // 重新加载数据
        } else {
            alert('回退失败: ' + data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('回退失败');
    });
});

// 表单提交
document.getElementById('filterForm').addEventListener('submit', function(e) {
    e.preventDefault();
    loadTransactions();
});

// 重置按钮
document.getElementById('resetBtn').addEventListener('click', function() {
    document.getElementById('filterForm').reset();
    loadTransactions();
});

// 页面加载完成后自动加载数据
document.addEventListener('DOMContentLoaded', function() {
    // 设置默认日期为今天
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('endDate').value = today;
    
    // 设置开始日期为7天前
    const weekAgo = new Date();
    weekAgo.setDate(weekAgo.getDate() - 7);
    document.getElementById('startDate').value = weekAgo.toISOString().split('T')[0];
    
    // 加载数据
    loadTransactions();
});

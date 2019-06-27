# -*- coding: utf-8 -*-
import requests
from scrapy import Selector

from zvt.api.common import generate_kdata_id
from zvt.api.technical import get_kdata
from zvt.domain import TradingLevel, SecurityType, Provider, Stock1DKdata, StoreCategory
from zvt.recorders.recorder import TimeSeriesFetchingStyle, FixedCycleDataRecorder
from zvt.utils.time_utils import get_year_quarters, is_same_date, to_pd_timestamp
from zvt.utils.utils import to_float


# this recorder is deprecated,because sina hfq factor could not get now
class StockKdataSinaSpider(FixedCycleDataRecorder):
    provider = Provider.SINA
    store_category = StoreCategory.stock_1d_kdata
    data_schema = Stock1DKdata

    def __init__(self, security_type=SecurityType.stock, exchanges=['sh', 'sz'], codes=None, batch_size=10,
                 force_update=False, sleeping_time=5, fetching_style=TimeSeriesFetchingStyle.end_size,
                 default_size=2000, contain_unfinished_data=False, level=TradingLevel.LEVEL_1DAY,
                 one_shot=True) -> None:
        super().__init__(security_type, exchanges, codes, batch_size, force_update, sleeping_time, fetching_style,
                         default_size, contain_unfinished_data, level, one_shot)

        self.current_factors = {}
        self.latest_factors = {}
        for security_item in self.securities:
            kdata = get_kdata(security_id=security_item.id, provider=self.provider,
                              level=self.level.value, order=Stock1DKdata.timestamp.desc(),
                              return_type='domain',
                              session=self.session)
            if kdata:
                self.current_factors[security_item.id] = kdata[0].factor

    def get_data_map(self):
        return {}

    def generate_domain_id(self, security_item, original_data):
        return generate_kdata_id(security_id=security_item.id, timestamp=original_data['timestamp'], level=self.level)

    def record(self, security_item, start, end, size, timestamps):
        the_quarters = get_year_quarters(start)
        # treat has recorded the season if contains some date
        if not is_same_date(security_item.timestamp, start) and len(the_quarters) > 1:
            the_quarters = the_quarters[1:]
        for year, quarter in the_quarters:
            kdatas = []

            for fuquan in ['bfq', 'hfq']:
                the_url = self.get_kdata_url(security_item.code, year, quarter, fuquan)
                resp = requests.get(the_url)

                trs = Selector(text=resp.text).xpath(
                    '//*[@id="FundHoldSharesTable"]/tr[position()>1 and position()<=last()]').extract()

                for idx, tr in enumerate(trs):
                    tds = Selector(text=tr).xpath('//td//text()').extract()
                    tds = [x.strip() for x in tds if x.strip()]

                    open = tds[1]
                    high = tds[2]
                    close = tds[3]
                    low = tds[4]
                    volume = tds[5]
                    turnover = tds[6]
                    if fuquan == 'hfq':
                        factor = tds[7]

                    the_timestamp = to_pd_timestamp(tds[0])
                    the_id = generate_kdata_id(security_id=security_item.id, timestamp=the_timestamp, level=self.level)

                    if fuquan == 'hfq':
                        # we got bfq at first and then update hfq data
                        existed = [item for item in kdatas if item['id'] == the_id]

                        if existed:
                            kdata = existed[0]
                        else:
                            self.logger.error("bfq not got for:{}".format(the_id))
                            kdata = {
                                'id': the_id,
                                'timestamp': the_timestamp,
                                'name': security_item.name,
                                'level': self.level.value,
                                'open': to_float(open) / to_float(factor),
                                'close': to_float(close) / to_float(factor),
                                'high': to_float(high) / to_float(factor),
                                'low': to_float(low) / to_float(factor),
                                'volume': to_float(volume),
                                'turnover': to_float(turnover)
                            }
                            kdatas.append(kdata)

                        kdata['hfq_open'] = to_float(open)
                        kdata['hfq_high'] = to_float(high)
                        kdata['hfq_close'] = to_float(close)
                        kdata['hfq_low'] = to_float(low)
                        kdata['factor'] = to_float(factor)

                        self.latest_factors[security_item.id] = to_float(factor)

                    else:
                        kdatas.append({
                            'id': the_id,
                            'timestamp': the_timestamp,
                            'name': security_item.name,
                            'level': self.level.value,
                            'open': to_float(open),
                            'close': to_float(close),
                            'high': to_float(high),
                            'low': to_float(low),
                            'volume': to_float(volume),
                            'turnover': to_float(turnover)
                        })

            return kdatas

    def on_finish(self, security_item):
        latest_factor = self.latest_factors.get(security_item.id)
        # if latest_factor != self.current_factors.get(security_item.id):
        if latest_factor:
            if latest_factor != self.current_factors.get(security_item.id):
                sql = 'UPDATE stock_1d_kdata SET qfq_close=hfq_close/{},qfq_high=hfq_high/{}, qfq_open= hfq_open/{}, qfq_low= hfq_low/{} where ' \
                      'provider =\'{}\' and security_id=\'{}\' and level=\'{}\' and (qfq_close isnull or qfq_high isnull or qfq_low isnull or qfq_open isnull)'.format(
                    latest_factor, latest_factor, latest_factor, latest_factor, self.provider.value, security_item.id,
                    self.level.value)
            else:
                sql = 'UPDATE stock_1d_kdata SET qfq_close=hfq_close/{},qfq_high=hfq_high/{}, qfq_open= hfq_open/{}, qfq_low= hfq_low/{} where ' \
                      'security_id=\'{}\' and level=\'{}\''.format(latest_factor, latest_factor,
                                                                   latest_factor,
                                                                   latest_factor,
                                                                   security_item.id,
                                                                   self.level.value)
            self.session.execute(sql)
            self.session.commit()

    def get_kdata_url(self, code, year, quarter, fuquan):
        if fuquan == 'hfq':
            return 'http://vip.stock.finance.sina.com.cn/corp/go.php/vMS_FuQuanMarketHistory/stockid/{}.phtml?year={}&jidu={}'.format(
                code, year, quarter)
        else:
            return 'http://vip.stock.finance.sina.com.cn/corp/go.php/vMS_MarketHistory/stockid/{}.phtml?year={}&jidu={}'.format(
                code, year, quarter)


if __name__ == '__main__':
    StockKdataSinaSpider(exchanges=['sz'], codes=['002937'], level=TradingLevel.LEVEL_1DAY).run()
